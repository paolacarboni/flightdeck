"""Indice dei repo locali per proporre la cartella di un ticket nuovo.

Candidati: repo git sotto ~/Projects fino a profondità 5, raggruppati per remote origin (clone e worktree
dello stesso repo sono un solo candidato). Per ogni candidato, frammenti di testo: nome, struttura,
README e sessioni Claude in cui ci si è lavorato. L'indice si costruisce fuori dal percorso di `start`
(`cc-panel index`, avviato in background dal pannello); i vettori li calcola `embed.py` nel venv.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from cc_panel import config, folders, history, paths

VERSION = 1
SEARCH_DEPTH = 5
MAX_AGE_SECONDS = 12 * 3600
LOCK_STALE_SECONDS = 15 * 60
README_NAMES = ("README.md", "README.MD", "readme.md", "README.rst", "README.txt", "README")
README_BLOCK = 800
README_BLOCKS = 3
STRUCTURE_LIMIT = 80
CHILDREN_LIMIT = 15
SESSION_LIMIT = 30
SESSION_TEXT_LIMIT = 500
SESSION_MAX_KEYS = 3
LABEL_LIMIT = 60
WORKTREES_DIR = ".worktrees"
_ORIGIN_SECTION = re.compile(r'^\s*\[remote\s+"origin"\]\s*$')
_URL = re.compile(r"^\s*url\s*=\s*(\S+)\s*$")
_GITDIR = re.compile(r"^gitdir:\s*(.+?)\s*$", re.M)
_CODE_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HTML = re.compile(r"<[^>]+>")
_PYPROJECT = re.compile(r'^\s*description\s*=\s*"([^"]+)"', re.M)
_POM = re.compile(r"<description>\s*([^<]+?)\s*</description>")


class VectorsError(Exception):
    pass


def index_dir():
    return paths.home() / ".claude/cc-panel/index"


def _is_repo(folder):
    return (folder / ".git").exists()


def _scan():
    root = config.projects_dir()
    found = []
    for current, dirs, _ in os.walk(root):
        here = Path(current)
        if here != root and _is_repo(here):
            found.append(here)
            worktrees = here / WORKTREES_DIR
            if worktrees.is_dir():
                found.extend(sorted(p for p in worktrees.iterdir() if p.is_dir() and _is_repo(p)))
            dirs[:] = []
            continue
        depth = len(here.relative_to(root).parts)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in folders.SKIP_DIRS) \
            if depth < SEARCH_DEPTH else []
    return found


def origin_name(git_dir):
    """Nome del repo dal remote origin in <git_dir>/config, senza .git; None se manca."""
    try:
        lines = (git_dir / "config").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    in_origin = False
    for line in lines:
        if line.strip().startswith("["):
            in_origin = bool(_ORIGIN_SECTION.match(line))
            continue
        match = _URL.match(line) if in_origin else None
        if match:
            name = match.group(1).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            return name[:-4] if name.endswith(".git") else name
    return None


def _main_git_dir(folder):
    """Cartella .git del repo principale: la propria, o quella indicata dal file .git di un worktree."""
    git = folder / ".git"
    if git.is_dir():
        return git
    try:
        match = _GITDIR.search(git.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if not match:
        return None
    gitdir = Path(match.group(1))
    if not gitdir.is_absolute():
        gitdir = (folder / gitdir).resolve()
    main = gitdir.parent.parent if gitdir.parent.name == "worktrees" else gitdir
    return main if main.is_dir() else None


def candidates():
    """Un candidato per repo: {"group", "folder" (clone principale), "folders", "names"}."""
    groups = {}
    for folder in _scan():
        git_dir = _main_git_dir(folder)
        remote = origin_name(git_dir) if git_dir else None
        key = "origin:%s" % remote if remote else str(git_dir.parent if git_dir else folder)
        group = groups.setdefault(key, {"group": key, "folders": [], "names": [], "remote": remote})
        group["folders"].append(folder)
    found = []
    for group in groups.values():
        members = sorted(group["folders"], key=str)
        clones = [f for f in members if (f / ".git").is_dir()]
        names = []
        for name in [f.name for f in members] + ([group["remote"]] if group["remote"] else []):
            if name not in names:
                names.append(name)
        found.append({"group": group["group"], "folder": str((clones or members)[0]),
                      "folders": [str(f) for f in members], "names": names})
    return sorted(found, key=lambda c: c["folder"])


def _manifest_description(folder):
    try:
        return json.loads((folder / "package.json").read_text(encoding="utf-8")).get("description") or ""
    except (OSError, ValueError, AttributeError):
        pass
    for name, pattern in (("pyproject.toml", _PYPROJECT), ("pom.xml", _POM)):
        try:
            match = pattern.search((folder / name).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if match:
            return match.group(1)
    return ""


def _visible(entry):
    return not entry.name.startswith(".") and entry.name not in folders.SKIP_DIRS


def _structure(folder):
    names = []
    try:
        entries = sorted(e for e in folder.iterdir() if _visible(e))
    except OSError:
        return ""
    for entry in entries:
        names.append(entry.name)
        if entry.is_dir():
            try:
                children = sorted(c for c in entry.iterdir() if c.is_dir() and _visible(c))[:CHILDREN_LIMIT]
            except OSError:
                children = []
            names.extend("%s/%s" % (entry.name, c.name) for c in children)
    return " ".join(names[:STRUCTURE_LIMIT])


def _readme(folder):
    """Testo del README senza blocchi di codice, immagini, badge e HTML; righe vuote compattate."""
    for name in README_NAMES:
        try:
            text = (folder / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _HTML.sub(" ", _LINK.sub(r"\1", _IMAGE.sub(" ", _CODE_FENCE.sub(" ", text))))
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return ""


def _readme_title(text):
    for line in text.splitlines():
        title = line.lstrip("#").strip()
        if title:
            return title[:LABEL_LIMIT]
    return ""


def _common_parents(parts, folder):
    common = 0
    for mine, theirs in zip(reversed(parts), reversed(folder.parts[:-1])):
        if mine != theirs:
            break
        common += 1
    return common


def _owner_function(candidates_):
    """Indice del candidato che contiene un percorso. Un percorso che non esiste più (cartelle riorganizzate)
    si ritrova per nome di cartella: a parità, vince il candidato con più cartelle genitrici uguali; ambiguo → None."""
    members = [(i, Path(f)) for i, c in enumerate(candidates_) for f in c["folders"]]
    by_name = {}
    for index, folder in members:
        by_name.setdefault(folder.name, []).append((index, folder))

    def owner(path):
        best, depth = None, -1
        for index, folder in members:
            if (path == folder or folder in path.parents) and len(folder.parts) > depth:
                best, depth = index, len(folder.parts)
        if best is not None or path.exists():
            return best
        scored = sorted(((_common_parents(path.parts[:position], folder), position, index)
                         for position, part in enumerate(path.parts) for index, folder in by_name.get(part, [])),
                        reverse=True)
        if not scored:
            return None
        if len(scored) > 1 and scored[1][:2] == scored[0][:2] and scored[1][2] != scored[0][2]:
            return None
        return scored[0][2]
    return owner


def _attributed(sessions, candidates_):
    """Sessioni per candidato: dove ha modificato più file, altrimenti la cartella di partenza."""
    owner_of = _owner_function(candidates_)
    by_group = {}
    for session in sessions:
        if len(session["keys"]) > SESSION_MAX_KEYS:
            continue
        votes = {}
        for file in session.get("files") or []:
            owner = owner_of(Path(file))
            if owner is not None:
                votes[owner] = votes.get(owner, 0) + 1
        if votes:
            owner = max(votes, key=lambda i: (votes[i], -i))
        else:
            owner = owner_of(Path(session["cwd"])) if session.get("cwd") else None
        if owner is not None:
            by_group.setdefault(owner, []).append(session)
    return by_group


def _session_chunk(index, session):
    parts = [session.get("title")] + list(session.get("promptSample") or [])[:2]
    text = " ".join(" ".join(p.split()) for p in parts if p)[:SESSION_TEXT_LIMIT]
    label = (session.get("title") or (session.get("promptSample") or [""])[0] or "")[:LABEL_LIMIT]
    return {"group": index, "kind": "sessione", "label": "sessione «%s»" % label, "text": text}


def chunks(candidates_, sessions):
    projects = config.projects_dir()
    by_group = _attributed(sessions, candidates_)
    found = []
    for index, candidate in enumerate(candidates_):
        folder = Path(candidate["folder"])
        try:
            relative = str(folder.relative_to(projects))
        except ValueError:
            relative = str(folder)
        name = " ".join(p for p in [" ".join(candidate["names"]), relative.replace("/", " "),
                                    _manifest_description(folder)] if p)
        found.append({"group": index, "kind": "nome", "label": "nome", "text": name})
        found.append({"group": index, "kind": "struttura", "label": "struttura", "text": _structure(folder)})
        readme = _readme(folder)
        label = "README: %s" % _readme_title(readme)
        for start in range(0, min(len(readme), README_BLOCK * README_BLOCKS), README_BLOCK):
            found.append({"group": index, "kind": "readme", "label": label, "text": readme[start:start + README_BLOCK]})
        recent = sorted(by_group.get(index, []), key=lambda s: -s["mtime"])[:SESSION_LIMIT]
        found.extend(_session_chunk(index, s) for s in recent if s.get("title") or s.get("promptSample"))
    return found


def _acquire_lock():
    lock = index_dir() / "index.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                fresh = time.time() - float(lock.read_text(encoding="utf-8")) < LOCK_STALE_SECONDS
            except (OSError, ValueError):
                fresh = False
            if fresh:
                return False
            try:
                lock.unlink()
            except OSError:
                return False
            continue
        with os.fdopen(fd, "w") as handle:
            handle.write(str(time.time()))
        return True
    return False


def _write_json(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(str(temporary), str(path))


def _vectors_in_venv(folder):
    """Calcola i vettori con il python del venv; senza venv l'indice resta solo lessicale."""
    from cc_panel import semantic
    python = semantic.python()
    if not python:
        return
    try:
        result = subprocess.run([str(python), "-m", "cc_panel.embed", "index", str(folder)],
                                cwd=str(semantic.package_root()), stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=semantic.INDEX_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VectorsError(str(error)) from None
    if result.returncode != 0:
        raise VectorsError((result.stderr.strip().splitlines() or ["codice %d" % result.returncode])[-1])


def build(now=None, indexed=None, vectors=None):
    """Ricostruisce l'indice; None se un'altra costruzione è in corso. VectorsError se i vettori non si calcolano:
    meta.json resta scritto e la ricerca usa solo le parole."""
    if not _acquire_lock():
        return None
    try:
        candidates_ = candidates()
        meta = {"version": VERSION, "builtAt": now if now is not None else time.time(),
                "candidates": candidates_, "chunks": chunks(candidates_, history.index() if indexed is None else indexed)}
        _write_json(index_dir() / "meta.json", meta)
        (vectors or _vectors_in_venv)(index_dir())
        return meta
    finally:
        try:
            (index_dir() / "index.lock").unlink()
        except OSError:
            pass


def load():
    try:
        meta = json.loads((index_dir() / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("version") != VERSION:
        return None
    if not isinstance(meta.get("candidates"), list) or not isinstance(meta.get("chunks"), list):
        return None
    return meta


def is_stale(meta, now):
    return meta is None or now - meta.get("builtAt", 0) > MAX_AGE_SECONDS


def spawn_build():
    """Avvia `cc-panel index` staccato dal chiamante."""
    cli = Path(__file__).resolve().parent.parent / "bin" / "cc-panel"
    subprocess.Popen([str(cli), "index"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)

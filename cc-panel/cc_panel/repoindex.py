"""Indice dei repo locali per proporre la cartella di un ticket nuovo.

Candidati: repo git sotto ~/Projects fino a profondità 5, raggruppati per remote origin (clone e worktree
dello stesso repo sono un solo candidato). Per ogni candidato, frammenti di testo: nome, struttura,
README e sessioni Claude in cui ci si è lavorato. L'indice si costruisce fuori dal percorso di `start`
(`cc-panel index`, avviato in background dal pannello); i vettori li calcola `embed.py` nel venv.
Meta e vettori nuovi si preparano in file `.next` e si pubblicano insieme: chi legge vede sempre una coppia
coerente, salvo i millisecondi delle sostituzioni.
"""
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

from cc_panel import config, folders, history, paths, semantic

VERSION = 1
SEARCH_DEPTH = 5
MAX_AGE_SECONDS = 12 * 3600
# Oltre il timeout del calcolo dei vettori, più il tempo della scansione: una build viva non risulta mai scaduta.
LOCK_STALE_SECONDS = semantic.INDEX_TIMEOUT_SECONDS + 5 * 60
SPAWN_BACKOFF_SECONDS = 15 * 60
META = "meta.json"
VECTORS = "vectors.npy"
VECTORS_INFO = "vectors.json"
NEXT_META = "meta.next.json"
NEXT_VECTORS = "vectors.next.npy"
NEXT_VECTORS_INFO = "vectors.next.json"
CACHE = "cache.npz"
LOCK = "index.lock"
SPAWN_MARKER = "last-spawn"
README_NAMES = ("README.md", "README.MD", "readme.md", "README.rst", "README.txt", "README")
README_BLOCK = 800
README_BLOCKS = 3
STRUCTURE_LIMIT = 80
CHILDREN_LIMIT = 15
SESSION_LIMIT = 30
SESSION_TEXT_LIMIT = 500
SESSION_MAX_KEYS = 3
DISTINCTIVE_NAME = 8
LABEL_LIMIT = 60
WORKTREES_DIR = ".worktrees"
_ORIGIN_SECTION = re.compile(r'^\s*\[remote\s+"origin"\]\s*$')
_URL = re.compile(r"^\s*url\s*=\s*(\S+)\s*$")
_GITDIR = re.compile(r"^gitdir:\s*(.+?)\s*$", re.M)
_URL_WITH_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", re.I)
_SCP_LIKE = re.compile(r"^(?:[^@/]+@)?([^/:]+):(.+)$")
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


def _origin_url(git_dir):
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
            return match.group(1)
    return None


def origin(git_dir):
    """(chiave, nome) del remote origin: chiave = host/percorso senza utente, schema e .git, così https e ssh
    dello stesso repo coincidono e un fork resta distinto; (None, None) se manca."""
    url = _origin_url(git_dir) if git_dir else None
    if not url:
        return None, None
    url = url.rstrip("/")
    match = _URL_WITH_SCHEME.match(url) or _SCP_LIKE.match(url)
    key = "%s/%s" % (match.group(1).lower(), match.group(2)) if match else url
    key = key[:-4] if key.endswith(".git") else key
    return key, key.rsplit("/", 1)[-1]


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
        remote_key, remote = origin(git_dir)
        key = "origin:%s" % remote_key if remote_key else str(git_dir.parent if git_dir else folder)
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
        description = json.loads((folder / "package.json").read_text(encoding="utf-8")).get("description")
        if isinstance(description, str):
            return description
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


def _distinctive(name):
    """Nome abbastanza specifico da riconoscere una cartella spostata anche senza genitori in comune."""
    return len(name) >= DISTINCTIVE_NAME or "-" in name or "_" in name


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
        scored = sorted(((common, position, index)
                         for position, part in enumerate(path.parts) for index, folder in by_name.get(part, [])
                         for common in [_common_parents(path.parts[:position], folder)]
                         if common or _distinctive(part)),
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
    """Token del lock appena preso, None se un'altra build è viva. La scadenza si misura sull'mtime del file:
    un lock appena creato e ancora vuoto vale come vivo."""
    lock = index_dir() / LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    token = "%d-%s" % (os.getpid(), uuid.uuid4().hex)
    for _ in range(2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
            except OSError:
                continue
            if age < LOCK_STALE_SECONDS:
                return None
            try:
                lock.unlink()
            except OSError:
                return None
            continue
        with os.fdopen(fd, "w") as handle:
            handle.write(token)
        return token
    return None


def _release_lock(token):
    lock = index_dir() / LOCK
    try:
        if lock.read_text(encoding="utf-8") == token:
            lock.unlink()
    except OSError:
        pass


def _write_json(path, data):
    temporary = path.with_name("tmp-" + path.name)
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(str(temporary), str(path))


def _clean_next(folder):
    """File di una build non pubblicata (anche di una build morta a metà)."""
    for path in folder.glob("*"):
        if path.name in (NEXT_META, NEXT_VECTORS, NEXT_VECTORS_INFO) or path.name.startswith("tmp-"):
            try:
                path.unlink()
            except OSError:
                pass


def _publish(folder):
    """Sostituisce la coppia pubblicata: prima i vettori, per ultimo il meta."""
    for staged, published in ((NEXT_VECTORS, VECTORS), (NEXT_VECTORS_INFO, VECTORS_INFO)):
        if (folder / staged).exists():
            os.replace(str(folder / staged), str(folder / published))
    os.replace(str(folder / NEXT_META), str(folder / META))


def _vectors_in_venv(folder):
    """Calcola i vettori di meta.next.json con il python del venv; senza venv l'indice resta solo lessicale."""
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
    """Ricostruisce e pubblica l'indice; None se un'altra build è in corso.

    VectorsError se i vettori non si calcolano: resta pubblicata la coppia precedente; alla prima build si
    pubblica comunque il meta, che basta alla ricerca per parole.
    """
    token = _acquire_lock()
    if token is None:
        return None
    folder = index_dir()
    try:
        _clean_next(folder)
        candidates_ = candidates()
        meta = {"version": VERSION, "builtAt": now if now is not None else time.time(),
                "candidates": candidates_, "chunks": chunks(candidates_, history.index() if indexed is None else indexed)}
        _write_json(folder / NEXT_META, meta)
        try:
            (vectors or _vectors_in_venv)(folder)
        except VectorsError:
            if not (folder / META).exists():
                os.replace(str(folder / NEXT_META), str(folder / META))
            raise
        _publish(folder)
        return meta
    finally:
        _clean_next(folder)
        _release_lock(token)


def load():
    try:
        meta = json.loads((index_dir() / META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict) or meta.get("version") != VERSION:
        return None
    if not isinstance(meta.get("candidates"), list) or not isinstance(meta.get("chunks"), list):
        return None
    return meta


def is_stale(meta, now):
    return meta is None or now - meta.get("builtAt", 0) > MAX_AGE_SECONDS


def spawn_build(now=None):
    """Avvia `cc-panel index` staccato dal chiamante, al massimo una volta ogni 15 minuti; True se avviato."""
    now = time.time() if now is None else now
    marker = index_dir() / SPAWN_MARKER
    try:
        if now - float(marker.read_text(encoding="utf-8")) < SPAWN_BACKOFF_SECONDS:
            return False
    except (OSError, ValueError):
        pass
    cli = Path(__file__).resolve().parent.parent / "bin" / "cc-panel"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(now), encoding="utf-8")
        subprocess.Popen([str(cli), "index"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    return True

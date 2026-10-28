"""Indice delle sessioni Claude Code passate, ricavato dai transcript con cache incrementale.

Per ogni transcript: cartella di partenza, chiavi Jira citate nei messaggi di utente e
assistente (non negli output dei tool né nei messaggi di sistema), titolo della sessione.
"""
import json
import os
import re

from cc_panel import keys, paths

CACHE_VERSION = 3
LABEL_LIMIT = 80
SAMPLE_LIMIT = 200
SAMPLE_EDGE = 3
FILES_LIMIT = 10
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
_COMMIT = re.compile(r"\bgit\b[^|;&]*\bcommit\b")
_ANY_KEY = re.compile(r"(?<![A-Z0-9-])%s(?![0-9])" % keys.KEY_PATTERN)
_MESSAGE_MARKER = re.compile(r'"type":\s*"(?:user|assistant)"')
_USER_MARKER = re.compile(r'"type":\s*"user"')


def message_text(record):
    """Testo scritto da utente o assistente; vuoto per output dei tool e messaggi di sistema."""
    if record.get("type") not in ("user", "assistant") or record.get("isMeta"):
        return ""
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _prompt_text(record):
    """Messaggio scritto dall'utente; vuoto per comandi, output locali e messaggi di sistema."""
    if record.get("type") != "user" or record.get("isMeta"):
        return ""
    content = (record.get("message") or {}).get("content")
    text = content if isinstance(content, str) else ""
    return "" if text.lstrip().startswith("<") else text.strip()


def _scan(path):
    cwd, title, found, prompts, first = None, None, set(), 0, None
    edits, commits, files, sample = 0, 0, [], []
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            wanted_cwd = cwd is None and '"cwd"' in line
            is_title = '"custom-title"' in line
            # Filtri economici prima del parse: i transcript possono pesare molti MB.
            is_message = bool(_MESSAGE_MARKER.search(line) and _ANY_KEY.search(line))
            is_prompt = bool(_USER_MARKER.search(line)) and '"tool_result"' not in line
            is_tool = '"tool_use"' in line
            if not (wanted_cwd or is_title or is_message or is_prompt or is_tool):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if cwd is None:
                cwd = record.get("cwd")
            if record.get("type") == "custom-title":
                title = record.get("customTitle") or title
            if is_message:
                found.update(_ANY_KEY.findall(message_text(record)))
            prompt = _prompt_text(record) if is_prompt else ""
            if prompt:
                prompts += 1
                one_line = " ".join(prompt.split())
                if first is None:
                    first = one_line[:LABEL_LIMIT]
                sample.append(one_line[:SAMPLE_LIMIT])
            if is_tool and record.get("type") == "assistant":
                for block in (record.get("message") or {}).get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_input = block.get("input") or {}
                    if block.get("name") in EDIT_TOOLS:
                        edits += 1
                        path = tool_input.get("file_path") or tool_input.get("notebook_path")
                        if path and path not in files and len(files) < FILES_LIMIT:
                            files.append(path)
                    elif block.get("name") == "Bash" and _COMMIT.search(tool_input.get("command") or ""):
                        commits += 1
    if len(sample) > 2 * SAMPLE_EDGE:
        sample = sample[:SAMPLE_EDGE] + sample[-SAMPLE_EDGE:]
    return {"cwd": cwd, "keys": sorted(found), "title": title, "prompts": prompts, "firstPrompt": first,
            "edits": edits, "commits": commits, "files": files, "promptSample": sample}


def _cache_file():
    return paths.home() / ".claude/cc-panel/history.json"


def _load_cache():
    try:
        cache = json.loads(_cache_file().read_text(encoding="utf-8"))
        if cache.get("version") == CACHE_VERSION and isinstance(cache.get("files"), dict):
            return cache["files"]
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def index():
    cached = _load_cache()
    files, changed = {}, False
    for path in (paths.home() / ".claude/projects").glob("*/*.jsonl"):
        try:
            stat = path.stat()
            entry = cached.get(str(path))
            if not entry or entry.get("mtime") != stat.st_mtime or entry.get("size") != stat.st_size:
                entry = dict(_scan(path), mtime=stat.st_mtime, size=stat.st_size)
                changed = True
        except OSError:
            continue
        files[str(path)] = entry
    if changed or set(files) != set(cached):
        target = _cache_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        # Scrittura atomica: anche l'indicizzazione in background aggiorna questa cache.
        temporary = target.with_name("tmp-%d-%s" % (os.getpid(), target.name))
        temporary.write_text(json.dumps({"version": CACHE_VERSION, "files": files}), encoding="utf-8")
        os.replace(str(temporary), str(target))
    return [{"sessionId": path.rsplit("/", 1)[-1][:-len(".jsonl")], "cwd": entry["cwd"],
             "keys": set(entry["keys"]), "title": entry["title"], "mtime": entry["mtime"],
             "prompts": entry["prompts"], "firstPrompt": entry["firstPrompt"], "edits": entry["edits"],
             "commits": entry["commits"], "files": entry["files"], "promptSample": entry["promptSample"]}
            for path, entry in files.items()]

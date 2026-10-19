"""Sessioni Claude Code aperte, lette da ~/.claude/sessions."""
import json

from cc_panel import history, paths


def open_sessions():
    """Sessioni aperte, da ~/.claude/sessions; file non leggibili ignorati."""
    found = []
    for path in (paths.home() / ".claude/sessions").glob("*.json"):
        try:
            found.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found


def find_open(key, opened=None):
    """Sessione aperta più recente il cui nome è la chiave o inizia con «<chiave> »."""
    matches = [s for s in (open_sessions() if opened is None else opened) if _titled(s.get("name") or "", key)]
    return max(matches, key=lambda s: s.get("statusUpdatedAt") or 0, default=None)


def _titled(name, key):
    return name == key or name.startswith(key + " ")


def find_closed(key, indexed=None):
    """Ultima sessione (anche terminata) il cui titolo è la chiave o inizia con «<chiave> »."""
    indexed = history.index() if indexed is None else indexed
    titled = [s for s in indexed if s["title"] and _titled(s["title"], key)]
    if not titled:
        return None
    best = max(titled, key=lambda s: s["mtime"])
    return {"sessionId": best["sessionId"], "name": best["title"], "cwd": best["cwd"]}

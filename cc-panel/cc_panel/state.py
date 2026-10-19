"""Stato persistente di cc-panel in ~/.claude/cc-panel/state.json (cartelle, collegamenti, ignorate)."""
import json

from cc_panel import paths


def load():
    try:
        state = json.loads(paths.state_file().read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save(state):
    path = paths.state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")

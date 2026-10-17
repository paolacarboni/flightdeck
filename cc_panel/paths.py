"""Percorsi di cc-panel; la home è sovrascrivibile con CC_PANEL_HOME (test)."""
import os
from pathlib import Path



def home():
    return Path(os.environ.get("CC_PANEL_HOME") or Path.home())


def state_file():
    return home() / ".claude/cc-panel/state.json"


def briefs_dir():
    return home() / ".claude/cc-panel/briefs"


def ticket_note(key):
    from cc_panel import config
    return config.notes_dir() / ("%s.md" % key)

"""Configurazione utente in ~/.config/cc-panel/config.json; le variabili d'ambiente hanno la precedenza.

Chiavi: jira_base_url, jira_email, default_project, notes_dir, projects_dir.
Il token Jira non sta qui: si legge da JIRA_API_TOKEN.
"""
import json
import os
from pathlib import Path

from cc_panel import paths

ENV = {
    "jira_base_url": "CC_PANEL_JIRA_URL",
    "jira_email": "CC_PANEL_JIRA_EMAIL",
    "default_project": "CC_PANEL_DEFAULT_PROJECT",
    "notes_dir": "CC_PANEL_NOTES_DIR",
    "projects_dir": "CC_PANEL_PROJECTS_DIR",
}


class ConfigError(Exception):
    pass


def config_file():
    return paths.home() / ".config/cc-panel/config.json"


def _value(key):
    if os.environ.get(ENV[key]):
        return os.environ[ENV[key]]
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get(key) if isinstance(data, dict) else None


def _required(key):
    value = _value(key)
    if not value:
        raise ConfigError("Manca «%s»: impostalo in %s o con la variabile %s" % (key, config_file(), ENV[key]))
    return value


def _path(value):
    return Path(value.replace("~", str(paths.home()), 1) if value.startswith("~") else value)


def jira_base_url():
    return _required("jira_base_url").rstrip("/")


def jira_email():
    return _required("jira_email")


def default_project():
    return _value("default_project")


def notes_dir():
    return _path(_value("notes_dir") or "~/.cc-panel/notes")


def projects_dir():
    return _path(_value("projects_dir") or "~/Projects")

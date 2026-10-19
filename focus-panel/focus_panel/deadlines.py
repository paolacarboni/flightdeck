"""Scadenze dei prossimi giorni: voci locali con data + ticket Jira assegnati con duedate.

Jira si legge riusando il client di cc-panel (stessa configurazione e token). La lettura gira in
background (`focus-panel sync`) e finisce in una cache: il pannello non aspetta mai la rete.
"""
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from focus_panel import store

WINDOW_DAYS = 7
SYNC_SECONDS = 30 * 60
LOCK_STALE_SECONDS = 5 * 60
JQL = ("assignee = currentUser() AND statusCategory != Done AND duedate <= %dd ORDER BY duedate ASC"
       % WINDOW_DAYS)


class DeadlineError(Exception):
    pass


def _cache_file():
    return store.data_dir() / "deadlines.json"


def _lock_file():
    return store.data_dir() / "sync.lock"


def load_cache():
    try:
        cache = json.loads(_cache_file().read_text(encoding="utf-8"))
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def _locked():
    try:
        return time.time() - float(_lock_file().read_text(encoding="utf-8")) < LOCK_STALE_SECONDS
    except (OSError, ValueError):
        return False


def map_issues(issues, base_url):
    return [{"key": i["key"], "title": i["fields"]["summary"].strip(), "due": i["fields"]["duedate"],
             "url": "%s/browse/%s" % (base_url, i["key"])} for i in issues if i["fields"].get("duedate")]


def _cc_panel_root():
    # Di default cc-panel sta accanto a focus-panel, nello stesso repository.
    return Path(os.environ.get("FOCUS_PANEL_CC_PANEL") or Path(__file__).resolve().parents[2] / "cc-panel")


def fetch_jira():
    root = str(_cc_panel_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from cc_panel import config, jira
    except ImportError:
        raise DeadlineError("cc-panel non trovato in %s: niente scadenze Jira" % root) from None
    try:
        return map_issues(jira.search(JQL, ["summary", "duedate"]), config.jira_base_url())
    except (jira.JiraError, config.ConfigError) as error:
        raise DeadlineError(str(error)) from None


def sync(fetcher=None, now=None):
    now = time.time() if now is None else now
    cache = load_cache()
    lock = _lock_file()
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(time.time()), encoding="utf-8")
    try:
        items = (fetcher or fetch_jira)()
        cache = {"items": items, "error": None, "syncedAt": now, "attemptedAt": now}
    except DeadlineError as error:
        cache = dict(cache, items=cache.get("items", []), error=str(error), attemptedAt=now)
        cache.setdefault("syncedAt", None)
    finally:
        try:
            os.remove(str(lock))
        except OSError:
            pass
    _cache_file().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def _spawn_sync():
    """Avvia `focus-panel sync` staccato dal pannello."""
    cli = Path(__file__).resolve().parent.parent / "bin" / "focus-panel"
    subprocess.Popen([str(cli), "sync"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def _days(due, today):
    try:
        return (date.fromisoformat(due) - today).days
    except (TypeError, ValueError):
        return None


def collect(state, now):
    cache = load_cache()
    syncing = _locked()
    if not syncing and now - (cache.get("attemptedAt") or 0) >= SYNC_SECONDS:
        _spawn_sync()
        syncing = True
    today = date.fromisoformat(store.day_of(now))
    entries = [{"source": "jira", "key": i["key"], "title": i["title"], "due": i["due"], "url": i["url"]}
               for i in cache.get("items", [])]
    entries += [{"source": "local", "id": i["id"], "title": i["text"], "due": i["due"]}
                for i in state["items"] if i.get("due") and not i.get("doneAt")]
    for entry in entries:
        entry["days"] = _days(entry["due"], today)
    entries = [e for e in entries if e["days"] is not None and e["days"] <= WINDOW_DAYS]
    entries.sort(key=lambda e: (e["days"], e["title"]))
    return {"deadlines": entries, "jiraError": cache.get("error"), "syncing": syncing}

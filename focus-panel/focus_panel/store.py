"""Stato di focus-panel: voci del giorno, frog e time box, in ~/.claude/focus-panel/focus.json.

Regole: al massimo tre voci per giorno, un solo frog per giorno, un solo box attivo con una sola
proroga. Le voci non fatte dei giorni passati tornano nel parcheggio: si ri-decide, non si trascina.
"""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

MAX_PER_DAY = 3
MIN_MINUTES = 5
MAX_MINUTES = 240
EXTENSION_MINUTES = 10
WARN_SECONDS = 5 * 60
WHEN = ("oggi", "domani", "dopo")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FocusError(Exception):
    pass


def home():
    return Path(os.environ.get("FOCUS_PANEL_HOME") or Path.home())


def data_dir():
    return home() / ".claude/focus-panel"


def _state_file():
    return data_dir() / "focus.json"


def day_of(now, offset=0):
    return (datetime.fromtimestamp(now) + timedelta(days=offset)).strftime("%Y-%m-%d")


def load(now):
    try:
        state = json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = None
    if not isinstance(state, dict):
        state = {}
    state.setdefault("items", [])
    state.setdefault("box", None)
    state.setdefault("log", [])
    state.setdefault("nextId", max([i["id"] for i in state["items"]] + [0]) + 1)
    today = day_of(now)
    for item in state["items"]:
        if item["day"] and item["day"] < today and not item.get("doneAt"):
            item["day"], item["frog"] = None, False
    return state


def save(state):
    target = _state_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(temporary), str(target))


def find(state, item_id):
    for item in state["items"]:
        if item["id"] == item_id:
            return item
    raise FocusError("Voce %s inesistente" % item_id)


def _resolve_day(when, now):
    if when not in WHEN:
        raise FocusError("Quando: %s" % " | ".join(WHEN))
    return None if when == "dopo" else day_of(now, 0 if when == "oggi" else 1)


def _check_room(state, day, exclude=None):
    if day is None:
        return
    taken = [i for i in state["items"] if i["day"] == day and i is not exclude]
    if len(taken) >= MAX_PER_DAY:
        raise FocusError("Già %d voci per il %s: sposta qualcosa nel parcheggio" % (MAX_PER_DAY, day))


def add(state, text, minutes, when, due=None, frog=False, now=None):
    text = (text or "").strip()
    if not text:
        raise FocusError("Scrivi l'azione: verbo + oggetto")
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise FocusError("Durata tra %d e %d minuti" % (MIN_MINUTES, MAX_MINUTES))
    if due and not _DATE.match(due):
        raise FocusError("Scadenza nel formato AAAA-MM-GG")
    day = _resolve_day(when, now)
    _check_room(state, day)
    item = {"id": state["nextId"], "text": text, "minutes": minutes, "day": day, "frog": False,
            "due": due or None, "doneAt": None, "created": now}
    state["nextId"] += 1
    state["items"].append(item)
    if frog:
        set_frog(state, item["id"], now)
    return item


def set_frog(state, item_id, now=None):
    item = find(state, item_id)
    if not item["day"]:
        raise FocusError("Il frog va su oggi o domani, non nel parcheggio")
    for other in state["items"]:
        if other["day"] == item["day"]:
            other["frog"] = False
    item["frog"] = True
    return item


def move(state, item_id, when, now=None):
    item = find(state, item_id)
    day = _resolve_day(when, now)
    _check_room(state, day, exclude=item)
    if day != item["day"]:
        item["day"], item["frog"] = day, False
    return item


def drop(state, item_id):
    item = find(state, item_id)
    if state["box"] and state["box"]["itemId"] == item_id:
        state["box"] = None
    state["items"].remove(item)
    return item


# ------------------------------------------------------------------ time box

def start(state, item_id, minutes=None, now=None):
    if state["box"]:
        raise FocusError("C'è già un box attivo: una cosa alla volta")
    item = find(state, item_id)
    if item.get("doneAt"):
        raise FocusError("Voce già fatta")
    if item["day"] != day_of(now):
        raise FocusError("Il box si apre solo su voci di oggi")
    minutes = minutes or item["minutes"]
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise FocusError("Durata tra %d e %d minuti" % (MIN_MINUTES, MAX_MINUTES))
    state["box"] = {"itemId": item_id, "start": now, "minutes": minutes, "extended": False}
    return state["box"]


def _end(box):
    return box["start"] + (box["minutes"] + (EXTENSION_MINUTES if box["extended"] else 0)) * 60


def box_status(state, now):
    box = state["box"]
    if not box:
        return None
    end = _end(box)
    remaining = end - now
    phase = "over" if remaining < 0 else "warn" if remaining <= WARN_SECONDS else "run"
    return dict(box, end=end, remaining=remaining, phase=phase)


def extend(state, now=None):
    box = state["box"]
    if not box:
        raise FocusError("Nessun box attivo")
    if box["extended"]:
        raise FocusError("Proroga già usata: chiudi, fatto è meglio che perfetto")
    box["extended"] = True
    return box


def stop(state, now=None):
    box = state["box"]
    if not box:
        raise FocusError("Nessun box attivo")
    state["log"].append({"itemId": box["itemId"], "start": box["start"], "end": now,
                         "planned": box["minutes"], "over": box["extended"] or now > _end(box)})
    state["box"] = None
    return box


def done(state, item_id=None, now=None):
    if item_id is None:
        if not state["box"]:
            raise FocusError("Nessun box attivo: indica la voce")
        item_id = state["box"]["itemId"]
    item = find(state, item_id)
    if state["box"] and state["box"]["itemId"] == item_id:
        stop(state, now)
    item["doneAt"] = now
    return item


def over_today(state, now):
    today = day_of(now)
    return sum(1 for entry in state["log"] if entry["over"] and day_of(entry["end"]) == today)

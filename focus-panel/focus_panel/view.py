"""Vista per il pannello: voci di oggi e di domani, parcheggio, box attivo e scadenze."""
from datetime import datetime

from focus_panel import deadlines, store

FROG_UNTIL_HOUR = 12
PLAN_FROM_MINUTE = 17 * 60 + 30


def _ordered(items):
    """Prima il frog, poi le voci da fare, in fondo quelle fatte."""
    return sorted(items, key=lambda i: (bool(i.get("doneAt")), not i["frog"], i["id"]))


def show(now):
    state = store.load(now)
    moment = datetime.fromtimestamp(now)
    today, tomorrow = store.day_of(now), store.day_of(now, 1)
    today_items = _ordered([i for i in state["items"] if i["day"] == today])
    tomorrow_items = _ordered([i for i in state["items"] if i["day"] == tomorrow])
    frog = next((i for i in today_items if i["frog"]), None)
    box = store.box_status(state, now)
    if box:
        box["text"] = store.find(state, box["itemId"])["text"]
    data = {
        "now": now,
        "today": today_items,
        "tomorrow": tomorrow_items,
        "parked": [i for i in state["items"] if i["day"] is None],
        "frogFirst": bool(frog and not frog.get("doneAt") and moment.hour < FROG_UNTIL_HOUR),
        "planMode": moment.hour * 60 + moment.minute >= PLAN_FROM_MINUTE,
        "tomorrowFrog": any(i["frog"] for i in tomorrow_items),
        "box": box,
        "overToday": store.over_today(state, now),
        "doneToday": sum(1 for i in today_items if i.get("doneAt")),
        "maxPerDay": store.MAX_PER_DAY,
    }
    data.update(deadlines.collect(state, now))
    return data

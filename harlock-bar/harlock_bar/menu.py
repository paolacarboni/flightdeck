"""Menu xbar: countdown, main task del giorno, ticket in lavorazione e scadenze.

Funzione pura: riceve lo stato di focus-panel (`focus-panel show`), il modello di cc-panel
(`board.json`) e l'ora, e restituisce le righe nel formato dei plugin xbar.
"""
import math
from datetime import datetime

GREEN = "#49f07c"
AMBER = "#ffb84a"
RED = "#ff6b5e"
MAGENTA = "#ff5ef0"
CYAN = "#56e3ff"
DIM = "#7d8799"

DURATIONS = (15, 30, 60, 90)  # come i box di focus-panel
SUMMARY_LEN = 52


def clean(text, limit=None):
    """Testo sicuro per xbar: niente «|» (separa i parametri), niente a capo, niente «-» iniziali."""
    text = " ".join(str(text).replace("|", "¦").split()).lstrip("-")
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def line(text, **params):
    parts = ["%s=%s" % (key, value) for key, value in params.items() if value is not None]
    return "%s | %s" % (text, " ".join(parts)) if parts else text


def action(cmd, *args, refresh=True):
    params = {"shell": cmd}
    params.update(("param%d" % (i + 1), arg) for i, arg in enumerate(args))
    params["terminal"] = "false"
    if refresh:
        params["refresh"] = "true"
    return params


def minutes_left(seconds):
    return int(math.ceil(seconds / 60.0))


def minutes_over(remaining):
    """Minuti interi già passati oltre la fine del box (remaining negativo)."""
    return int(-remaining // 60)


# ------------------------------------------------------------------ titolo

def _waiting(board):
    return [t for t in in_progress(board) if _session_kind(t) == "waiting"]


def title(focus, board, ctx):
    box = (focus or {}).get("box")
    if box:
        if box["phase"] == "over":
            return line("+%d′" % minutes_over(box["remaining"]), image=ctx["icon"], color=RED)
        return line("%d′" % minutes_left(box["remaining"]), image=ctx["icon"],
                    color=AMBER if box["phase"] == "warn" else None)
    waiting = len(_waiting(board)) if board else 0
    return line("⏸%d" % waiting if waiting else "", image=ctx["icon"])


# ------------------------------------------------------------------ giornata

def _remaining_work(focus):
    box = focus.get("box")
    total = 0
    for it in focus["today"]:
        if it.get("doneAt"):
            continue
        if box and box["itemId"] == it["id"]:
            total += max(minutes_left(box["remaining"]), 0)
        else:
            total += it["minutes"]
    return total


def pace(focus, now, day_end):
    """Riga che dice come va la giornata rispetto ai main task: (testo, colore)."""
    today = focus["today"]
    if not today:
        return "Nessun main task per oggi: scegline al massimo %d" % focus.get("maxPerDay", 3), AMBER
    if all(it.get("doneAt") for it in today):
        return "Tutti i main task fatti ✓", GREEN
    current = datetime.fromtimestamp(now)
    end = current.replace(hour=day_end[0], minute=day_end[1], second=0, microsecond=0)
    left = int((end - current).total_seconds() // 60)
    work = _remaining_work(focus)
    if left <= 0:
        return "Giornata finita con %d′ di lavoro ancora aperto" % work, RED
    detail = "%d′ di lavoro, %d′ alla fine della giornata" % (work, left)
    if work <= left:
        return "In linea: " + detail, GREEN
    return "In ritardo di %d′: %s" % (work - left, detail), AMBER


def _box_lines(box, ctx):
    cmd = ctx["cmd"]
    if box["phase"] == "over":
        head = line("⏱ Tempo scaduto da %d′ · %s" % (minutes_over(box["remaining"]), clean(box["text"], SUMMARY_LEN)),
                    color=RED)
    else:
        head = line("⏱ %d′ rimasti · %s" % (minutes_left(box["remaining"]), clean(box["text"], SUMMARY_LEN)),
                    color=AMBER if box["phase"] == "warn" else GREEN)
    lines = [head, line("--✓ Fatto", **action(cmd, "focus", "done"))]
    if not box.get("extended"):
        lines.append(line("--+10′ (una volta sola)", **action(cmd, "focus", "extend")))
    lines.append(line("--■ Ferma il countdown", **action(cmd, "focus", "stop")))
    return lines


def _item_lines(it, focus, ctx):
    cmd = ctx["cmd"]
    text = clean(it["text"], SUMMARY_LEN)
    if it.get("doneAt"):
        return [line("✓ " + text, color=DIM)]
    mark = "◆ " if it.get("frog") else "○ "
    lines = [line("%s%s · %d′" % (mark, text, it["minutes"]), color=MAGENTA if it.get("frog") else None)]
    if not focus.get("box"):
        lines.append(line("--▶ Avvia countdown %d′ (stima)" % it["minutes"],
                          **action(cmd, "focus", "start", it["id"], "-m", it["minutes"])))
        lines += [line("--▶ %d′" % m, **action(cmd, "focus", "start", it["id"], "-m", m))
                  for m in DURATIONS if m != it["minutes"]]
        lines.append("-----")
    lines.append(line("--✓ Segna fatto", **action(cmd, "focus", "done", it["id"])))
    if not it.get("frog"):
        lines.append(line("--◆ Rendi frog", **action(cmd, "focus", "frog", it["id"])))
    lines.append(line("--→ Sposta a domani", **action(cmd, "focus", "move", it["id"], "domani")))
    lines.append(line("--⌫ Parcheggia", **action(cmd, "focus", "move", it["id"], "dopo")))
    return lines


def day_section(focus, now, ctx):
    if focus is None:
        return [line("Main task: focus-panel non risponde", color=RED)]
    today = focus["today"]
    done = sum(1 for it in today if it.get("doneAt"))
    lines = [line("Main task di oggi · %d/%d fatti" % (done, len(today)), size=12)]
    text, color = pace(focus, now, ctx["day_end"])
    lines.append(line(text, color=color))
    if focus.get("overToday"):
        lines.append(line("Box fuori tempo oggi: %d" % focus["overToday"], color=AMBER))
    if focus.get("frogFirst"):
        lines.append(line("Prima la rana: il frog non è ancora fatto", color=MAGENTA))
    if focus.get("box"):
        lines += _box_lines(focus["box"], ctx)
    for it in today:
        lines += _item_lines(it, focus, ctx)
    if len(today) < focus.get("maxPerDay", 3):
        lines.append(line("+ Aggiungi main task…", **action(ctx["cmd"], "add", "oggi")))
    if focus.get("planMode"):
        tomorrow = focus.get("tomorrow", [])
        color = None if focus.get("tomorrowFrog") else AMBER
        lines.append(line("Domani · %d voci%s" % (len(tomorrow), "" if focus.get("tomorrowFrog") else ", manca il frog"),
                          color=color))
        lines += [line("--%s%s" % ("◆ " if it.get("frog") else "○ ", clean(it["text"], SUMMARY_LEN))) for it in tomorrow]
        lines.append(line("--+ Aggiungi per domani…", **action(ctx["cmd"], "add", "domani")))
    return lines


# ------------------------------------------------------------------ ticket

def in_progress(board):
    tickets = [t for epic in board.get("epics", []) for t in epic.get("items", [])]
    tickets += board.get("noEpic", [])
    return [t for t in tickets if t.get("statusCategory") == "indeterminate"]


def _session_kind(ticket):
    session = ticket.get("session") or {}
    if session.get("state") != "open":
        return "none"
    if session.get("status") == "waiting":
        return "waiting"
    return "stale" if session.get("staleDays") else "open"


ORDER = {"waiting": 0, "open": 1, "stale": 2, "none": 3}
MARK = {"waiting": "⏸", "open": "▶", "stale": "⚠", "none": "·"}
MAX_ACTIVE = 5
# Un colore per epica, leggibili sul menu chiaro e su quello scuro.
EPIC_COLORS = ("#4fa3e0", "#e0a33a", "#b07be0", "#3cc6a0", "#e0607e", "#8a9be8", "#c0b030", "#e07a3a")
NO_EPIC = {"key": None, "summary": "Senza epica"}


def _groups(board):
    """Epiche con almeno un ticket in lavorazione, ognuna con il suo colore; per ultimi i ticket senza epica."""
    groups = []
    for epic in board.get("epics", []) + [dict(NO_EPIC, items=board.get("noEpic", []))]:
        tickets = in_progress({"epics": [epic]})
        if tickets:
            groups.append((epic, tickets))
    return [(epic, tickets, EPIC_COLORS[i % len(EPIC_COLORS)] if epic["key"] else DIM)
            for i, (epic, tickets) in enumerate(groups)]


def _ticket_actions(t, board, ctx, depth):
    sub = "--" * depth
    kind = _session_kind(t)
    lines = []
    if kind == "waiting":
        lines.append(line(sub + "La sessione Claude ti sta aspettando", color=AMBER))
    elif kind == "stale":
        lines.append(line(sub + "Sessione ferma da %s g: /park e /exit" % t["session"]["staleDays"], color=AMBER))
    if t.get("nextStep"):
        lines.append(line(sub + "Prossimo passo: " + clean(t["nextStep"], 90), size=12))
    lines.append(line(sub + "Apri su Jira", href="%s/browse/%s" % (board["baseUrl"], t["key"])))
    lines.append(line(sub + "Riprendi la sessione", **action(ctx["cmd"], "start", t["key"], refresh=False)))
    return lines


def ticket_section(board, now, ctx):
    """In alto i ticket con una sessione Claude aperta; il resto in un sottomenu per epica, ognuna col suo colore."""
    if not board:
        return [line("Ticket: dati non ancora disponibili", color=DIM)]
    groups = _groups(board)
    color_of = {t["key"]: color for _, tickets, color in groups for t in tickets}
    total = sum(len(tickets) for _, tickets, _ in groups)
    updated = datetime.fromtimestamp(board.get("updatedAt", now)).strftime("%H:%M")
    lines = [line("Ticket in lavorazione · %d · Jira delle %s" % (total, updated), size=12)]
    active = sorted((t for _, tickets, _ in groups for t in tickets if _session_kind(t) != "none"),
                    key=lambda t: ORDER[_session_kind(t)])
    for t in active[:MAX_ACTIVE]:
        lines.append(line("%s %s %s" % (MARK[_session_kind(t)], t["key"], clean(t["summary"], SUMMARY_LEN)),
                          color=color_of[t["key"]]))
        lines += _ticket_actions(t, board, ctx, 1)
    for epic, tickets, color in groups:
        lines.append(line("● %s · %d" % (clean(epic["summary"], 40), len(tickets)), color=color))
        if epic["key"]:
            lines.append(line("--Apri l'epica %s" % epic["key"], href="%s/browse/%s" % (board["baseUrl"], epic["key"])))
            lines.append("-----")
        for t in sorted(tickets, key=lambda t: ORDER[_session_kind(t)]):
            mark = MARK[_session_kind(t)]
            lines.append(line("--%s%s %s" % ("" if mark == "·" else mark + " ", t["key"], clean(t["summary"], SUMMARY_LEN)),
                              color=color))
            lines += _ticket_actions(t, board, ctx, 2)
    proposals = board.get("proposals") or []
    if proposals:
        lines.append(line("Lavoro senza ticket da tracciare: %d (vedi cc-panel)" % len(proposals), color=CYAN))
    return lines


# ------------------------------------------------------------------ scadenze

def _when(days):
    if days < 0:
        return "scaduta da %d g" % -days, RED
    if days == 0:
        return "oggi", AMBER
    return ("domani" if days == 1 else "tra %d g" % days), None


def deadline_section(focus):
    """Una riga con il conteggio; il dettaglio nel sottomenu."""
    deadlines = (focus or {}).get("deadlines") or []
    if not deadlines:
        return []
    overdue = sum(1 for d in deadlines if d["days"] < 0)
    head = "Scadenze · %d" % len(deadlines) + (", %d scadute" % overdue if overdue else "")
    lines = [line(head, color=RED if overdue else None)]
    for d in deadlines:
        when, color = _when(d["days"])
        name = clean(("%s %s" % (d["key"], d["title"])) if d.get("key") else d["title"], SUMMARY_LEN)
        lines.append(line("--%s · %s" % (name, when), href=d.get("url"), color=color))
    if focus.get("jiraError"):
        lines.append(line("--Jira: " + clean(focus["jiraError"], 80), color=RED))
    return lines


# ------------------------------------------------------------------ menu

DAYS = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")
MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


def today_label(now):
    """Data in italiano senza dipendere dal locale del processo (xbar parte con quello C)."""
    d = datetime.fromtimestamp(now)
    return "%s %d %s, %02d:%02d" % (DAYS[d.weekday()], d.day, MONTHS[d.month - 1], d.hour, d.minute)


def build(focus, board, now, ctx):
    lines = [title(focus, board, ctx), "---"]
    lines.append(line("Arcadia · " + today_label(now), size=12, color=DIM))
    lines += day_section(focus, now, ctx)
    lines.append("---")
    lines += ticket_section(board, now, ctx)
    deadlines = deadline_section(focus)
    if deadlines:
        lines.append("---")
        lines += deadlines
    lines.append("---")
    lines.append(line("Aggiorna i ticket da Jira", **action(ctx["cmd"], "board")))
    return lines

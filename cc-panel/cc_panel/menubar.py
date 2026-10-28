"""Menu xbar del feed: in barra lo stato delle sessioni, nel menu sessioni attive e decisioni di oggi.

Funzione pura: riceve il modello di `feed.build`, l'ora e il percorso di cc-panel e restituisce le
righe nel formato dei plugin xbar. I dettagli stanno nei sottomenu, al primo livello solo l'essenziale.
"""
import textwrap
from pathlib import Path

AMBER = "#ffb84a"
DIM = "#8a8f98"
LINE_LEN = 70
WRAP = 64
TODAY_DECISIONS = 6


def clean(text, limit=None):
    """Testo sicuro per xbar: niente «|» (separa i parametri), niente a capo, niente «-» iniziali."""
    text = " ".join(str(text).replace("|", "¦").split()).lstrip("-").strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def line(text, **params):
    parts = ["%s=%s" % (key, value) for key, value in params.items() if value is not None]
    return "%s | %s" % (text, " ".join(parts)) if parts else text


def wrapped(text, prefix="--", **params):
    return [line(prefix + chunk, **params) for chunk in textwrap.wrap(clean(text), WRAP)]


def _clock(ts):
    return ts[11:16]


def _label(session, home):
    if session.get("cwd") and Path(session["cwd"]) == Path(home):
        return "~"
    return session.get("project") or session["session"][:8]


def title(sessions):
    waiting = sum(s["status"] == "waiting" for s in sessions)
    working = sum(s["status"] == "working" for s in sessions)
    if waiting:
        return line("⏸ %d" % waiting, color=AMBER)
    if working:
        return "● %d" % working
    return line("○", color=DIM)


def session_section(sessions, home):
    lines = [line("Sessioni", size=12, color=DIM)]
    for s in sessions:
        if s["status"] == "idle":
            continue
        label = _label(s, home)
        if s["status"] == "waiting":
            lines.append(line(clean("⏸ %s  ti aspetta" % label, LINE_LEN), color=AMBER))
        else:
            lines.append(clean("● %s  %s" % (label, s["prompt"]), LINE_LEN))
        if s["prompt"]:
            lines += wrapped(s["prompt"])
        lines.append(line("--aggiornata alle %s" % _clock(s["updatedAt"]), color=DIM, size=12))
    idle = [s for s in sessions if s["status"] == "idle"]
    if idle:
        lines.append(line("%d inattive" % len(idle), color=DIM))
        lines += [line("--" + clean("%s · %s  %s" % (_label(s, home), _clock(s["updatedAt"]), s["prompt"]), LINE_LEN),
                       color=DIM) for s in idle]
    if len(lines) == 1:
        lines.append(line("Nessuna sessione attiva", color=DIM))
    return lines


def decision_details(d, cmd):
    lines = [line("--%s · %s" % (clean(d.get("project") or "~"), _clock(d["ts"])), color=DIM, size=12)]
    if d.get("why"):
        lines += wrapped(d["why"])
    if d.get("alternatives"):
        lines += wrapped("Scartate: " + "; ".join(d["alternatives"]), color=DIM)
    if d.get("watch"):
        lines += wrapped("⚠ " + d["watch"], color=AMBER)
    lines.append("-----")
    what = "«%s»" % clean(d["learn"], 40) if d.get("learn") else "la decisione"
    lines.append(line("--Approfondisci %s" % what, shell=cmd, param1="dive", param2=d["id"], terminal="false"))
    return lines


def decision_section(decisions, now, cmd):
    if not decisions:
        return []
    today = now.date().isoformat()
    top = [d for d in decisions if d["ts"].startswith(today)][:TODAY_DECISIONS]
    rest = [d for d in decisions if d not in top]
    lines = ["---", line("Decisioni di oggi", size=12, color=DIM)]
    for d in top:
        lines.append(clean(d["title"], LINE_LEN))
        lines += decision_details(d, cmd)
    if not top:
        lines.append(line("Nessuna decisione oggi", color=DIM))
    if rest:
        lines.append(line("Altre %d" % len(rest), color=DIM))
        for d in rest:
            day = "" if d["ts"].startswith(today) else d["ts"][8:10] + "/" + d["ts"][5:7] + " "
            lines.append("--" + clean("%s%s  %s" % (day, _clock(d["ts"]), d["title"]), LINE_LEN))
            lines += ["--" + sub for sub in decision_details(d, cmd)]
    return lines


def render(model, now, cmd, home=None):
    home = home or Path.home()
    return ([title(model["sessions"]), "---"] + session_section(model["sessions"], home)
            + decision_section(model["decisions"], now, cmd))

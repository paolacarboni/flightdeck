"""Feed live delle sessioni Claude: eventi dagli hook e decisioni dichiarate, in ~/.claude/cc-panel/events.jsonl."""
import json
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from cc_panel import paths

HOOK_KINDS = {"SessionStart": "start", "UserPromptSubmit": "prompt", "Notification": "attention",
              "Stop": "idle", "SessionEnd": "end"}
STATUS = {"start": "idle", "prompt": "working", "plan": "working", "attention": "waiting", "idle": "idle"}
TEXT_LIMIT = 200
STALE_AFTER = timedelta(hours=24)
MAX_DECISIONS = 50


def _append(record):
    path = paths.events_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _kind(payload):
    name = payload.get("hook_event_name")
    if name == "PostToolUse":
        return "plan" if payload.get("tool_name") == "ExitPlanMode" else None
    return HOOK_KINDS.get(name)


def record_hook(payload, now):
    """Registra l'evento di un hook; None (e nessuna scrittura) se non è un evento del feed."""
    if not isinstance(payload, dict) or not payload.get("session_id"):
        return None
    kind = _kind(payload)
    if kind is None:
        return None
    record = {"ts": now.isoformat(timespec="seconds"), "session": payload["session_id"],
              "cwd": payload.get("cwd") or "", "kind": kind}
    text = payload.get("prompt") if kind == "prompt" else payload.get("message") if kind == "attention" else None
    if text:
        record["text"] = str(text)[:TEXT_LIMIT]
    return _append(record)


def decide(session_id, cwd, title, why="", alternatives=(), watch="", learn="", now=None):
    """Registra una decisione importante dichiarata da una sessione."""
    record = {"ts": (now or datetime.now()).isoformat(timespec="seconds"), "session": session_id,
              "cwd": str(cwd), "kind": "decision", "id": secrets.token_hex(3), "title": title}
    optional = {"why": why, "alternatives": list(alternatives), "watch": watch, "learn": learn}
    record.update({key: value for key, value in optional.items() if value})
    return _append(record)


def load():
    """Eventi registrati, in ordine; righe illeggibili ignorate."""
    try:
        lines = paths.events_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("session") and event.get("kind"):
            events.append(event)
    return events


def build(events, now):
    """Modello del feed: sessioni attive, decisioni recenti e punti da attenzionare."""
    sessions = {}
    for event in events:
        session = sessions.setdefault(event["session"], {"session": event["session"], "status": "idle",
                                                         "prompt": "", "decisions": 0})
        session["cwd"] = event.get("cwd") or session.get("cwd", "")
        session["project"] = Path(session["cwd"]).name
        session["updatedAt"] = event["ts"]
        kind = event["kind"]
        if kind == "decision":
            session["decisions"] += 1
        elif kind == "end":
            session["status"] = "ended"
        else:
            session["status"] = STATUS.get(kind, session["status"])
        if kind == "prompt" and event.get("text"):
            session["prompt"] = event["text"]
        if kind == "attention":
            session["attention"] = event.get("text", "")
    cutoff = (now - STALE_AFTER).isoformat(timespec="seconds")
    active = [s for s in sessions.values() if s["status"] != "ended" and s["updatedAt"] >= cutoff]
    active.sort(key=lambda s: s["updatedAt"], reverse=True)
    decisions = [dict(e, project=Path(e.get("cwd") or "").name) for e in events if e["kind"] == "decision"]
    decisions.reverse()
    attention = [{"ts": s["updatedAt"], "session": s["session"], "project": s["project"], "text": s["attention"]}
                 for s in active if s["status"] == "waiting"]
    attention += [{"ts": d["ts"], "session": d["session"], "project": d["project"], "text": d["watch"], "id": d["id"]}
                  for d in decisions if d.get("watch") and d["ts"] >= cutoff]
    attention.sort(key=lambda a: a["ts"], reverse=True)
    return {"sessions": active, "decisions": decisions[:MAX_DECISIONS], "attention": attention}


def _clock(ts):
    return ts[11:16]


def render_text(model):
    lines = ["SESSIONI"]
    for s in model["sessions"]:
        lines.append("  %-8s %s  %s  %s" % (s["status"], _clock(s["updatedAt"]), s["project"] or s["session"][:8],
                                            s["prompt"][:80]))
    if not model["sessions"]:
        lines.append("  nessuna sessione attiva")
    if model["attention"]:
        lines.append("\nDA ATTENZIONARE")
        lines += ["  ⚠ %s  %s  %s" % (_clock(a["ts"]), a["project"], a["text"]) for a in model["attention"]]
    lines.append("\nDECISIONI")
    for d in model["decisions"]:
        lines.append("  %s  [%s] %s — %s" % (_clock(d["ts"]), d["project"], d["title"], d["id"]))
        if d.get("why"):
            lines.append("      perché: %s" % d["why"])
        if d.get("alternatives"):
            lines.append("      scartate: %s" % "; ".join(d["alternatives"]))
        if d.get("learn"):
            lines.append("      approfondisci: %s  (cc-panel dive %s)" % (d["learn"], d["id"]))
    if not model["decisions"]:
        lines.append("  nessuna decisione registrata")
    return "\n".join(lines)


def find(decision_id, events=None):
    """Ultima decisione con quell'id, o None."""
    matches = [e for e in (load() if events is None else events)
               if e["kind"] == "decision" and e.get("id") == decision_id]
    return matches[-1] if matches else None


def dive_prompt(decision):
    """Domanda per la fork di approfondimento."""
    if decision.get("learn"):
        return ("Voglio imparare «%s», usato nella decisione «%s» di questa sessione. Spiegamelo da zero, "
                "con un esempio preso da questo codice, quando conviene e quando no. Non modificare file."
                % (decision["learn"], decision["title"]))
    return ("Spiegami la decisione «%s» di questa sessione: contesto, alternative scartate, rischi e cosa "
            "dovrei verificare. Non modificare file." % decision["title"])

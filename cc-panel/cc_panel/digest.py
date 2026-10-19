"""Valutazione delle sessioni senza ticket: solo il lavoro di valore diventa una proposta.

Una sessione è candidata se ha prove di lavoro (file modificati o commit). Claude Haiku la valuta
una volta, con le epiche e le attività dell'utente come contesto, e propone titolo, motivo ed
eventuale epica o ticket esistente. Gli esiti restano in cache.
"""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cc_panel import history, llm, paths, tracking
from cc_panel.keys import TICKET_NAME

MIN_PROMPTS = 3
MIN_EDITS = 3
WINDOW_DAYS = 14
REEVALUATE_AFTER_HOURS = 6
LOCK_STALE_SECONDS = 15 * 60
CLAUDE_TIMEOUT_SECONDS = 180
WORKERS = 3

SCHEMA = {
    "type": "object",
    "properties": {
        "valuable": {"type": "boolean"},
        "title": {"type": "string"},
        "why": {"type": "string"},
        "existingKey": {"type": ["string", "null"]},
        "epicKey": {"type": ["string", "null"]},
    },
    "required": ["valuable", "title", "why", "existingKey", "epicKey"],
    "additionalProperties": False,
}

PROMPT = """Aiuti l'utente a tenere traccia del proprio lavoro su Jira. Valuta UNA sessione di lavoro con Claude Code.

È lavoro di valore se ha prodotto o fatto avanzare un risultato concreto legato ai suoi obiettivi: codice,
configurazione, automazione, documento, analisi conclusa. NON è di valore: domande veloci, consultazioni,
prove esplorative abbandonate, sistemazioni personali banali, sessioni interrotte senza risultato.

Epiche dell'utente:
{epics}

Attività aperte dell'utente:
{items}

Sessione nella cartella «{folder}» ({cwd}):
- messaggi dell'utente (estratto):
{sample}
- file modificati: {files}
- modifiche a file: {edits}; commit: {commits}

Rispondi con:
- valuable: true solo se è lavoro di valore come definito sopra;
- title: titolo di ticket in italiano, verbo all'infinito, massimo 70 caratteri, specifico;
- why: una riga, massimo 100 caratteri, cosa è stato fatto;
- existingKey: la chiave di un'attività aperta elencata che descrive già questo lavoro, altrimenti null;
- epicKey: la chiave dell'epica elencata più adatta, altrimenti null.
"""


MAX_GROUPS = 5

GROUP_SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "maxItems": MAX_GROUPS, "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "why": {"type": "string"},
                       "epicKey": {"type": ["string", "null"]},
                       "sessionIds": {"type": "array", "items": {"type": "string"}}},
        "required": ["title", "why", "epicKey", "sessionIds"], "additionalProperties": False}}},
    "required": ["groups"],
    "additionalProperties": False,
}

GROUP_PROMPT = """Aiuti l'utente a tracciare su Jira il lavoro di valore che non ha ancora un ticket.
Sotto ci sono sessioni di lavoro già giudicate di valore. Molte riguardano lo stesso tema.

Raggruppale per tema e restituisci AL MASSIMO {limit} gruppi, solo i più importanti rispetto alle sue
epiche (lavoro sostanziale e recente prima; lascia fuori il resto). Per ogni gruppo:
- title: titolo di ticket in italiano, verbo all'infinito, massimo 70 caratteri;
- why: una riga, massimo 110 caratteri, cosa è stato fatto nel complesso;
- epicKey: la chiave dell'epica elencata più adatta, altrimenti null;
- sessionIds: gli id delle sessioni del gruppo, presi dall'elenco.

Epiche dell'utente:
{epics}

Sessioni (id | data | cartella | titolo proposto | cosa è stato fatto):
{sessions}
"""


class DigestError(Exception):
    pass


def _cache_file():
    return paths.home() / ".claude/cc-panel/digest.json"


def _groups_file():
    return paths.home() / ".claude/cc-panel/groups.json"


def _load_groups():
    try:
        saved = json.loads(_groups_file().read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_groups(saved):
    target = _groups_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")


def groups():
    return _load_groups().get("groups", [])


def ungrouped(candidates_, cache):
    """Candidate valutate di valore e senza ticket esistente: la materia dei gruppi."""
    result = []
    for session in candidates_:
        evaluation = (cache.get(session["sessionId"]) or {}).get("result") or {}
        if evaluation.get("valuable") and not evaluation.get("existingKey"):
            result.append((session, evaluation))
    return result


def input_hash(candidates_, cache):
    material = sorted("%s|%s" % (s["sessionId"], e.get("title")) for s, e in ungrouped(candidates_, cache))
    return hashlib.sha256("\n".join(material).encode()).hexdigest()


def _lock_file():
    return paths.home() / ".claude/cc-panel/digest.lock"


def load():
    try:
        cache = json.loads(_cache_file().read_text(encoding="utf-8"))
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(cache):
    target = _cache_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def candidates(indexed, linked, ignored, now):
    """Sessioni recenti, senza ticket, con prove di lavoro."""
    return [s for s in indexed
            if s["sessionId"] not in linked and s["sessionId"] not in ignored
            and not TICKET_NAME.match(s["title"] or "")
            and now - s["mtime"] <= WINDOW_DAYS * 86400
            and s["prompts"] >= MIN_PROMPTS and (s["edits"] >= MIN_EDITS or s["commits"] >= 1)]


def _needs_evaluation(session, cache, now):
    cached = cache.get(session["sessionId"])
    if not cached:
        return True
    changed = cached.get("mtime") != session["mtime"]
    return changed and now - cached.get("evaluatedAt", 0) >= REEVALUATE_AFTER_HOURS * 3600


def pending(indexed, linked, ignored, now):
    """Valutazioni mancanti, più 1 se i gruppi non corrispondono più alle sessioni di valore."""
    cache = load()
    found = candidates(indexed, linked, ignored, now)
    todo = sum(1 for s in found if _needs_evaluation(s, cache, now))
    saved = _load_groups().get("inputHash")
    # Senza gruppi salvati conta solo se c'è materia da raggruppare.
    stale = saved != input_hash(found, cache) and (saved is not None or bool(ungrouped(found, cache)))
    return todo + (1 if stale else 0)


def evaluate(session, context, runner):
    lines = lambda entries: "\n".join("- %s %s" % (e["key"], e["summary"]) for e in entries) or "- nessuna"
    prompt = PROMPT.format(
        epics=lines(context["epics"]), items=lines(context["items"]),
        folder=Path(session["cwd"] or "?").name, cwd=session["cwd"] or "?",
        sample="\n".join("  · %s" % text for text in session["promptSample"]) or "  · (nessuno)",
        files=", ".join(session["files"]) or "nessuno", edits=session["edits"], commits=session["commits"])
    return runner(prompt)


def claude_runner(prompt):
    schema = GROUP_SCHEMA if prompt.startswith(GROUP_PROMPT[:40]) else SCHEMA
    try:
        return llm.structured(prompt, schema, CLAUDE_TIMEOUT_SECONDS)
    except llm.LLMError as error:
        raise DigestError("valutazione non riuscita: %s" % error) from None


def _context():
    try:
        board = json.loads((paths.home() / ".claude/cc-panel/board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    items = [i for e in board.get("epics", []) for i in e.get("items", [])] + board.get("noEpic", [])
    return {"epics": [{"key": e["key"], "summary": e["summary"]} for e in board.get("epics", [])],
            "items": [{"key": i["key"], "summary": i["summary"]} for i in items]}


def _acquire_lock():
    lock = _lock_file()
    try:
        if time.time() - float(lock.read_text(encoding="utf-8")) < LOCK_STALE_SECONDS:
            return False
    except (OSError, ValueError):
        pass
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(time.time()), encoding="utf-8")
    return True


def _autolink(cache, context):
    """Collega le sessioni il cui lavoro è già un'attività aperta; scarta chiavi sconosciute."""
    mine = {item["key"] for item in context["items"]}
    linked = tracking.links()
    changed = False
    for session_id, entry in cache.items():
        key = (entry.get("result") or {}).get("existingKey")
        if not key:
            continue
        if key in mine:
            if session_id not in linked:
                tracking.link(session_id, key)
        else:
            entry["result"]["existingKey"] = None
            changed = True
    if changed:
        _save(cache)


def _group(indexed, cache, context, runner, now):
    found = candidates(indexed, tracking.links(), tracking.ignored(), now)
    material = ungrouped(found, cache)
    digest_hash = input_hash(found, cache)
    if _load_groups().get("inputHash") == digest_hash:
        return
    if not material:
        _save_groups({"inputHash": digest_hash, "groups": []})
        return
    lines = "\n".join("%s | %s | %s | %s | %s" % (
        s["sessionId"], time.strftime("%Y-%m-%d", time.localtime(s["mtime"])), Path(s["cwd"] or "?").name,
        e.get("title"), e.get("why")) for s, e in sorted(material, key=lambda m: -m[0]["mtime"]))
    epics = "\n".join("- %s %s" % (e["key"], e["summary"]) for e in context["epics"]) or "- nessuna"
    try:
        answer = runner(GROUP_PROMPT.format(limit=MAX_GROUPS, epics=epics, sessions=lines))
    except DigestError:
        return
    valid_ids = {s["sessionId"] for s, _ in material}
    epic_keys = {e["key"] for e in context["epics"]}
    result = []
    for group in (answer.get("groups") or [])[:MAX_GROUPS]:
        ids = [sid for sid in group.get("sessionIds", []) if sid in valid_ids]
        if ids:
            result.append({"title": group.get("title"), "why": group.get("why"), "sessionIds": ids,
                           "epicKey": group.get("epicKey") if group.get("epicKey") in epic_keys else None})
    _save_groups({"inputHash": digest_hash, "groups": result})


def run(indexed=None, runner=claude_runner, now=None, workers=WORKERS):
    """Valuta le candidate mancanti; restituisce quante ne ha valutate."""
    if not _acquire_lock():
        return 0
    try:
        context = _context()
        if context is None:
            return 0
        now = time.time() if now is None else now
        indexed = history.index() if indexed is None else indexed
        cache = load()
        todo = [s for s in candidates(indexed, tracking.links(), tracking.ignored(), now)
                if _needs_evaluation(s, cache, now)]

        guard = threading.Lock()
        done = []

        def one(session):
            try:
                result = evaluate(session, context, runner)
            except DigestError:
                return
            # Ogni esito va subito su disco: il pannello lo mostra e un'interruzione non lo perde.
            with guard:
                cache[session["sessionId"]] = {"mtime": session["mtime"], "evaluatedAt": now, "result": result}
                _save(cache)
                done.append(session["sessionId"])
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, todo))
        _autolink(cache, context)
        _group(indexed, cache, context, runner, now)
        return len(done)
    finally:
        try:
            os.remove(str(_lock_file()))
        except OSError:
            pass

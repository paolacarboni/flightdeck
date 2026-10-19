"""Edizione quotidiana della rassegna: raccolta, sintesi con Claude Haiku e cache per il pannello.

Il pannello legge la cache (`show`); quando manca l'edizione di oggi avvia `news-panel fetch` in
background, che raccoglie le notizie e chiede a Haiku i temi caldi e le letture consigliate.
"""
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from news_panel import sources

EDITION_HOUR = 7
RETRY_SECONDS = 3600
LOCK_STALE_SECONDS = 15 * 60
CLAUDE_TIMEOUT_SECONDS = 240
MAX_TOPICS = 6
MAX_PICKS = 5
PROMPT_SUMMARY_CHARS = 160
AREAS = ["AI", "LLM", "RICERCA", "TECH"]

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "topics": {"type": "array", "maxItems": MAX_TOPICS, "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "summary": {"type": "string"},
                           "area": {"type": "string", "enum": AREAS}, "heat": {"type": "integer"},
                           "itemIds": {"type": "array", "items": {"type": "string"}}},
            "required": ["title", "summary", "area", "heat", "itemIds"], "additionalProperties": False}},
        "picks": {"type": "array", "maxItems": MAX_PICKS, "items": {
            "type": "object",
            "properties": {"itemId": {"type": "string"}, "why": {"type": "string"}},
            "required": ["itemId", "why"], "additionalProperties": False}},
    },
    "required": ["headline", "topics", "picks"],
    "additionalProperties": False,
}

PROMPT = """Prepari la rassegna quotidiana per una persona che sviluppa software con AI, LLM e agenti di sviluppo.
Sotto ci sono le notizie delle ultime 36 ore da fonti selezionate (id | fonte | punteggio | titolo | estratto).
Il punteggio è il voto della comunità (Hacker News, Lobsters, Hugging Face): «-» se la fonte non ne ha.

Individua gli argomenti caldi: temi ripresi da più fonti o con molto seguito, e novità con impatto
pratico (nuovi modelli, strumenti, tecniche, risultati di ricerca, mosse delle aziende, sicurezza).
Ignora promozioni, notizie marginali e doppioni. Scrivi tutto in italiano, conciso e concreto.

Rispondi con:
- headline: una frase, massimo 110 caratteri, che riassume la giornata;
- topics: al massimo {topics} temi, dal più caldo; per ognuno title (massimo 60 caratteri),
  summary (massimo 220 caratteri: cosa è successo e perché conta), area tra {areas},
  heat da 1 a 5, itemIds con gli id delle notizie del tema (le più rilevanti prima, massimo 4);
- picks: al massimo {picks} letture che valgono il tempo (analisi, tutorial, paper importanti),
  con itemId e why (massimo 90 caratteri).

Notizie:
{items}
"""


class EditionError(Exception):
    pass


def home():
    return Path(os.environ.get("NEWS_PANEL_HOME") or Path.home())


def _cache_file():
    return home() / ".claude/news-panel/news.json"


def _lock_file():
    return home() / ".claude/news-panel/fetch.lock"


def load():
    try:
        cache = json.loads(_cache_file().read_text(encoding="utf-8"))
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    target = _cache_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(target)


def _locked():
    try:
        return time.time() - float(_lock_file().read_text(encoding="utf-8")) < LOCK_STALE_SECONDS
    except (OSError, ValueError):
        return False


def _today(now):
    return datetime.fromtimestamp(now).strftime("%Y-%m-%d")


def _needs_fetch(cache, now):
    if cache.get("edition") == _today(now):
        return False
    if now - cache.get("attemptedAt", 0) < RETRY_SECONDS:
        return False
    # La prima edizione si prepara subito; le successive dalle 7, quando le newsletter sono uscite.
    return not cache or datetime.fromtimestamp(now).hour >= EDITION_HOUR


def _spawn_fetch():
    """Avvia `news-panel fetch` staccato dal pannello: raccolta e sintesi richiedono un minuto o due."""
    cli = Path(__file__).resolve().parent.parent / "bin" / "news-panel"
    subprocess.Popen([str(cli), "fetch"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def show(now=None):
    """Edizione in cache per il pannello; avvia la raccolta se manca quella di oggi."""
    now = time.time() if now is None else now
    cache = load()
    fetching = _locked()
    if not fetching and _needs_fetch(cache, now):
        _spawn_fetch()
        fetching = True
    return dict(cache, fetching=fetching)


def _score(item):
    return item["score"] if item.get("score") is not None else -1


def _fallback_picks(items):
    return sorted(items, key=lambda i: (_score(i), i.get("published") or 0), reverse=True)[:MAX_PICKS]


def summarize(items, runner):
    """Temi caldi e letture consigliate; senza Haiku, le notizie più votate."""
    by_id = {"n%d" % (index + 1): entry for index, entry in enumerate(items)}
    lines = "\n".join("%s | %s | %s | %s | %s" % (
        key, entry["source"], "-" if entry.get("score") is None else entry["score"], entry["title"],
        (entry.get("summary") or "")[:PROMPT_SUMMARY_CHARS]) for key, entry in by_id.items())
    try:
        answer = runner(PROMPT.format(topics=MAX_TOPICS, picks=MAX_PICKS, areas=", ".join(AREAS), items=lines))
    except EditionError as error:
        return {"headline": "", "topics": [], "picks": _fallback_picks(items),
                "error": "Sintesi non disponibile (%s): notizie più votate" % error}
    topics = []
    for topic in (answer.get("topics") or [])[:MAX_TOPICS]:
        found = [by_id[key] for key in topic.get("itemIds", []) if key in by_id]
        if found:
            topics.append({"title": topic.get("title", ""), "summary": topic.get("summary", ""),
                           "area": topic.get("area") if topic.get("area") in AREAS else "TECH",
                           "heat": max(1, min(5, int(topic.get("heat") or 1))), "items": found[:4]})
    picks = [dict(by_id[p["itemId"]], why=p.get("why", "")) for p in (answer.get("picks") or [])
             if p.get("itemId") in by_id][:MAX_PICKS]
    return {"headline": answer.get("headline", ""), "topics": topics, "picks": picks}


def claude_runner(prompt):
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    command = [claude, "-p", "--model", "haiku", "--no-session-persistence", "--tools", "",
               "--output-format", "json", "--json-schema", json.dumps(SCHEMA)]
    try:
        result = subprocess.run(command, input=prompt, capture_output=True, text=True,
                                timeout=CLAUDE_TIMEOUT_SECONDS, cwd=str(home()))
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise EditionError(str(error)[:120]) from None
    if result.returncode != 0 or payload.get("is_error") or not isinstance(payload.get("structured_output"), dict):
        raise EditionError(str(payload.get("result") or result.stderr)[:120])
    return payload["structured_output"]


def run(collector=None, runner=claude_runner, now=None):
    """Prepara l'edizione di oggi e la salva; restituisce i dati salvati."""
    if _locked():
        return load()
    lock = _lock_file()
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(time.time()), encoding="utf-8")
    try:
        now = time.time() if now is None else now
        collector = collector or (lambda moment: sources.collect(now=moment))
        items, status = collector(now)
        if not items:
            errors = "; ".join("%s: %s" % (s["name"], s.get("error")) for s in status if not s["ok"])
            data = dict(load(), attemptedAt=now, sources=status,
                        error="Nessuna notizia raccolta" + (" (%s)" % errors if errors else ""))
        else:
            data = {"edition": _today(now), "updatedAt": now, "attemptedAt": now, "count": len(items),
                    "sources": status}
            data.update(summarize(items, runner))
        _save(data)
        return data
    finally:
        try:
            os.remove(str(lock))
        except OSError:
            pass

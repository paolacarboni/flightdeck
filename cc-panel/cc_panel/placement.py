"""Cartelle proposte per un ticket nuovo: ricerca ibrida sull'indice dei repo, entro 2 secondi.

Due classifiche dei candidati di `repoindex`: BM25 sulle parole del ticket (stdlib) e similarità dei vettori
multilingual-e5 calcolata dal python del venv (`embed.py`). Le unisce la Reciprocal Rank Fusion; un repo
citato per nome nel ticket vale come un primo posto. Senza venv, oltre il budget o con errori del lato
denso restano le parole; senza indice nessuna proposta e l'indice si costruisce in background.
"""
import json
import math
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

from cc_panel import repoindex, semantic

DESCRIPTION_LIMIT = 1500
COMMENT_LIMIT = 300
LIMIT = 3
BUDGET_SECONDS = 2.0
MIN_DENSE_SECONDS = 0.3
FUSION_RESERVE_SECONDS = 0.1
RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75
NAME_MIN = 6
EVIDENCE_TERMS = 4
MENTIONED = "nome citato nel ticket"
_TOKEN = re.compile(r"[0-9a-zà-ÿ]+")
_NOT_ALNUM = re.compile(r"[^0-9a-z]")
STOPWORDS = frozenset("""
a ad al alla alle ai agli all anche che chi con cosa come da dal dalla dei del della delle dello di e ed
fa fare gli ha hai ho i il in la le lo ma mi ne nei nel nella non o per piu più puoi se si sia sono su sul
sulla tra fra un una uno va vedi questo questa quello quella
an and are as at be by for from has have in is it its of on or that the this to was with
""".split())


class DenseError(Exception):
    """Lato denso non disponibile; `rebuild` se la causa è un indice da ricostruire."""

    def __init__(self, message, rebuild=False):
        super().__init__(message)
        self.rebuild = rebuild


def query_text(issue):
    parts = [issue["summary"], issue.get("epic_summary") or "", (issue.get("description") or "")[:DESCRIPTION_LIMIT]]
    parts += ["%s: %s" % (c["author"], " ".join(c["body"].split())[:COMMENT_LIMIT]) for c in issue.get("comments") or []]
    return "\n".join(p for p in parts if p)


def tokens(text):
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS]


def bm25(docs, query):
    tokenized = [tokens(doc) for doc in docs]
    count = len(tokenized)
    average = (sum(len(doc) for doc in tokenized) / count) if count else 0
    frequency = Counter(term for doc in tokenized for term in set(doc))
    terms = set(tokens(query))
    scores = []
    for doc in tokenized:
        counts, score = Counter(doc), 0.0
        for term in terms:
            if counts[term]:
                idf = math.log(1 + (count - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += idf * counts[term] * (BM25_K1 + 1) / (
                    counts[term] + BM25_K1 * (1 - BM25_B + BM25_B * len(doc) / (average or 1)))
        scores.append(score)
    return scores


def _normal(text):
    return _NOT_ALNUM.sub("", text.lower())


def mentioned(candidate, text):
    """Il nome (o il remote) del candidato compare nel testo, ignorando maiuscole e separatori."""
    haystack = _normal(text)
    return any(len(name) >= NAME_MIN and name in haystack for name in (_normal(n) for n in candidate["names"]))


def fuse(rankings, boosts):
    """Reciprocal Rank Fusion: somma di 1/(k + posizione) sulle liste; un nome citato vale un primo posto."""
    scores = Counter()
    for ranking in rankings:
        for position, item in enumerate(ranking, 1):
            scores[item] += 1.0 / (RRF_K + position)
    for item in boosts:
        scores[item] += 1.0 / (RRF_K + 1)
    return sorted(scores, key=lambda item: (-scores[item], item))


class DenseProcess:
    """Il figlio `embed query` del venv. Avviato in anticipo carica il modello mentre il chiamante prepara il
    testo; richiamato con (testo, timeout) restituisce {candidato: (punteggio, frammento)}."""

    def __init__(self, python, popen=None):
        command = [str(python), "-m", "cc_panel.embed", "query", str(repoindex.index_dir())]
        self.process = (popen or subprocess.Popen)(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                                   stderr=subprocess.PIPE, text=True, cwd=str(semantic.package_root()))

    def __call__(self, text, timeout):
        try:
            stdout, stderr = self.process.communicate(text, timeout=timeout)
        except subprocess.TimeoutExpired:
            self.close()
            raise DenseError("oltre %.1f s" % timeout) from None
        if self.process.returncode != 0:
            last = (stderr.strip().splitlines() or ["codice %d" % self.process.returncode])[-1][:200]
            raise DenseError(last, rebuild=last.startswith("IndexMismatch"))
        try:
            return {int(group): (float(score), int(chunk)) for group, score, chunk in json.loads(stdout)["groups"]}
        except (ValueError, KeyError, TypeError) as error:
            raise DenseError("risposta non valida: %s" % error) from None

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def warm_up():
    """Avvia il lato denso senza aspettarlo; None se la ricerca semantica non è installata."""
    python = semantic.python()
    if python is None:
        return None
    try:
        return DenseProcess(python)
    except OSError:
        return None


def _dense(text, timeout):
    python = semantic.python()
    if python is None:
        raise DenseError("non installata: cc-panel semantic-setup")
    try:
        process = DenseProcess(python)
    except OSError as error:
        raise DenseError(str(error)) from None
    try:
        return process(text, timeout)
    finally:
        process.close()


def _key_pattern(key):
    """La chiave intera nel nome di una cartella: `OPS-586` trova `ops586` e `x-OPS-586-y`, non `ops-5860` né `xops-586`."""
    project, number = key.lower().rsplit("-", 1)
    return re.compile(r"(?<![a-z0-9])%s-?%s(?![0-9])" % (re.escape(project), number))


def _aligned(scores, chunks, count):
    """Ogni punteggio denso indica un candidato dell'indice e un frammento di quel candidato."""
    return all(0 <= group < count and 0 <= chunk < len(chunks) and chunks[chunk]["group"] == group
               for group, (_, chunk) in scores.items())


def _folder(candidate, key):
    """Cartella esistente del candidato: il worktree che contiene la chiave, altrimenti il clone principale."""
    members = [Path(f) for f in candidate["folders"]]
    pattern = _key_pattern(key)
    keyed = [f for f in members if pattern.search(f.name.lower())]
    for folder in keyed + [Path(candidate["folder"])] + members:
        if folder.is_dir():
            return folder
    return None


def _common_terms(doc, query):
    """Parole del ticket presenti nel candidato, le più lunghe (più specifiche) prima."""
    return sorted(set(tokens(query)) & set(tokens(doc)), key=lambda term: (-len(term), term))[:EVIDENCE_TERMS]


def rank(issue, limit=LIMIT, budget=BUDGET_SECONDS, dense=None, clock=time.monotonic, warn=lambda message: None):
    """Fino a `limit` (cartella, evidenza) per il ticket, entro `budget` secondi; [] senza indice."""
    started = clock()
    meta = repoindex.load()
    if meta is None:
        repoindex.spawn_build()
        return []
    if repoindex.is_stale(meta, time.time()):
        repoindex.spawn_build()
    candidates_, chunks = meta["candidates"], meta["chunks"]
    text = query_text(issue)
    docs = [[] for _ in candidates_]
    for chunk in chunks:
        docs[chunk["group"]].append(chunk["text"])
    docs = ["\n".join(doc) for doc in docs]
    lexical = bm25(docs, text)
    rankings = [[i for i in sorted(range(len(docs)), key=lambda i: -lexical[i]) if lexical[i] > 0]]
    scores = {}
    remaining = budget - (clock() - started) - FUSION_RESERVE_SECONDS
    if remaining < MIN_DENSE_SECONDS:
        warn("ricerca semantica saltata (tempo esaurito): uso solo le parole del ticket")
    else:
        try:
            scores = (dense or _dense)(text, remaining)
            if not _aligned(scores, chunks, len(candidates_)):
                scores = {}
                raise DenseError("vettori non allineati all'indice", rebuild=True)
        except DenseError as error:
            warn("ricerca semantica non disponibile (%s): uso solo le parole del ticket%s"
                 % (error, "; ricostruisco l'indice in background" if error.rebuild else ""))
            if error.rebuild:
                repoindex.spawn_build()
    if scores:
        rankings.append(sorted(scores, key=lambda group: -scores[group][0]))
    boosts = {i for i, candidate in enumerate(candidates_) if mentioned(candidate, text)}
    results = []
    for group in fuse(rankings, boosts):
        folder = _folder(candidates_[group], issue["key"])
        if folder is None:
            continue
        if group in boosts:
            evidence = MENTIONED
        elif group in scores:
            evidence = chunks[scores[group][1]]["label"]
        else:
            evidence = "parole in comune: %s" % ", ".join(_common_terms(docs[group], text))
        results.append((folder, evidence))
        if len(results) == limit:
            break
    return results

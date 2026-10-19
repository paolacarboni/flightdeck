"""Fonti della rassegna: solo feed e API pubbliche, nessuno scraping HTML.

Ogni fonte produce notizie nello stesso formato: titolo, url, fonte, area, punteggio (se la fonte
ne ha uno), data di pubblicazione, breve riassunto, link alla discussione.
"""
import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

WINDOW_HOURS = 36
PER_SOURCE = 15
SUMMARY_CHARS = 280
TIMEOUT_SECONDS = 20
USER_AGENT = "Mozilla/5.0 (Macintosh) news-panel/1.0"

HN_URL = "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=50&numericFilters=created_at_i>{since},points>60"

SOURCES = [
    {"id": "willison", "name": "Simon Willison", "kind": "feed", "area": "LLM", "url": "https://simonwillison.net/atom/everything/"},
    {"id": "latent", "name": "Latent Space", "kind": "feed", "area": "AI", "url": "https://www.latent.space/feed"},
    {"id": "interconnects", "name": "Interconnects", "kind": "feed", "area": "LLM", "url": "https://www.interconnects.ai/feed"},
    {"id": "importai", "name": "Import AI", "kind": "feed", "area": "AI", "url": "https://jack-clark.net/feed/"},
    {"id": "hfpapers", "name": "HF Papers", "kind": "hf", "area": "RICERCA", "url": "https://huggingface.co/api/daily_papers?limit=30",
     "windowHours": 72},
    {"id": "hfblog", "name": "Hugging Face", "kind": "feed", "area": "LLM", "url": "https://huggingface.co/blog/feed.xml"},
    {"id": "openai", "name": "OpenAI", "kind": "feed", "area": "LLM", "url": "https://openai.com/news/rss.xml"},
    {"id": "deepmind", "name": "Google DeepMind", "kind": "feed", "area": "LLM", "url": "https://deepmind.google/blog/rss.xml"},
    {"id": "localllama", "name": "r/LocalLLaMA", "kind": "feed", "area": "LLM", "url": "https://www.reddit.com/r/LocalLLaMA/top/.rss?t=day"},
    {"id": "hn", "name": "Hacker News", "kind": "hn", "area": "TECH", "url": HN_URL},
    {"id": "lobsters", "name": "Lobsters", "kind": "lobsters", "area": "TECH", "url": "https://lobste.rs/hottest.json"},
    {"id": "techmeme", "name": "Techmeme", "kind": "feed", "area": "TECH", "url": "https://www.techmeme.com/feed.xml"},
    {"id": "ars", "name": "Ars Technica", "kind": "feed", "area": "TECH", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
]

TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")


def _text(raw):
    """Testo semplice da un frammento HTML (anche doppiamente codificato), accorciato."""
    plain = SPACES.sub(" ", TAG.sub(" ", html.unescape(raw or ""))).strip()
    plain = re.sub(r"\s+([.,;:!?])", r"\1", plain)
    return plain if len(plain) <= SUMMARY_CHARS else plain[:SUMMARY_CHARS - 1].rstrip() + "…"


def _timestamp(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    # ISO 8601: fromisoformat di Python 3.9 non accetta «Z» né frazioni diverse da 3 o 6 cifre.
    iso = re.sub(r"\.\d+", "", raw.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(node, *names):
    for child in node:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text
    return None


def _link(node):
    for child in node:
        if _local(child.tag) != "link":
            continue
        if child.get("href") and child.get("rel", "alternate") == "alternate":
            return child.get("href")
        if (child.text or "").strip():
            return child.text.strip()
    return None


def _item(title, url, published, summary="", score=None, comments_url=None):
    return {"title": _text(title), "url": url, "published": published, "summary": _text(summary),
            "score": score, "commentsUrl": comments_url}


def parse_feed(text):
    """Voci di un feed RSS 2.0 o Atom."""
    root = ElementTree.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title, url = _child(node, "title"), _link(node)
        if not title or not url:
            continue
        items.append(_item(title, url, _timestamp(_child(node, "pubDate", "published", "updated", "date")),
                           _child(node, "description", "summary", "content") or ""))
    return items


def parse_hn(text):
    items = []
    for hit in json.loads(text).get("hits", []):
        discussion = "https://news.ycombinator.com/item?id=%s" % hit["objectID"]
        items.append(_item(hit.get("title"), hit.get("url") or discussion, hit.get("created_at_i"),
                           score=hit.get("points"), comments_url=discussion))
    return items


def parse_lobsters(text):
    return [_item(story["title"], story.get("url") or story["comments_url"], _timestamp(story.get("created_at")),
                  ", ".join(story.get("tags", [])), story.get("score"), story["comments_url"])
            for story in json.loads(text)]


def parse_hf(text):
    items = []
    for entry in json.loads(text):
        paper = entry.get("paper", {})
        url = "https://huggingface.co/papers/%s" % paper.get("id")
        items.append(_item(entry.get("title") or paper.get("title"), url,
                           _timestamp(paper.get("submittedOnDailyAt") or entry.get("publishedAt")),
                           paper.get("ai_summary") or paper.get("summary") or "", paper.get("upvotes"), url))
    return items


PARSERS = {"feed": parse_feed, "hn": parse_hn, "lobsters": parse_lobsters, "hf": parse_hf}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def _rank(item):
    return (item["score"] or 0, item["published"] or 0)


def _one(source, now, fetcher):
    # HF Papers non esce nel weekend: finestra più lunga per non restare vuoto.
    since = now - source.get("windowHours", WINDOW_HOURS) * 3600
    url = source["url"].format(since=int(since))
    found = [i for i in PARSERS[source["kind"]](fetcher(url)) if i["published"] and i["published"] >= since]
    found = sorted(found, key=_rank, reverse=True)[:PER_SOURCE]
    for entry in found:
        entry.update(source=source["name"], area=source["area"])
    return found


def collect(catalog=None, now=None, fetcher=fetch):
    """Notizie delle ultime WINDOW_HOURS ore da ogni fonte, e l'esito di ciascuna."""
    catalog = SOURCES if catalog is None else catalog

    def attempt(source):
        try:
            return _one(source, now, fetcher), None
        except Exception as error:  # una fonte rotta non deve fermare la rassegna
            return [], "%s: %s" % (type(error).__name__, error)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(attempt, catalog))
    items, status = [], []
    for source, (found, error) in zip(catalog, results):
        items.extend(found)
        entry = {"name": source["name"], "ok": error is None, "count": len(found)}
        if error:
            entry["error"] = error[:200]
        status.append(entry)
    return items, status

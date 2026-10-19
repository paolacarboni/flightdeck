import json
import unittest
from datetime import datetime, timezone

from news_panel import sources
from tests.helpers import FIXTURES

NOW = datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc).timestamp()


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseTest(unittest.TestCase):
    def test_rss_strips_html_and_reads_dates(self):
        items = sources.parse_feed(fixture("rss.xml"))
        self.assertEqual(items[0]["title"], "Nuovo modello & benchmark")
        self.assertEqual(items[0]["url"], "https://ex.com/a")
        self.assertEqual(items[0]["summary"], "Un modello nuovo.")
        self.assertEqual(items[0]["published"], datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc).timestamp())

    def test_atom_links_and_iso_dates(self):
        items = sources.parse_feed(fixture("atom.xml"))
        self.assertEqual([i["url"] for i in items], ["https://ex.com/atom", "https://ex.com/z"])
        self.assertEqual(items[0]["summary"], "Riassunto")
        self.assertEqual(items[1]["summary"], "Corpo")
        self.assertEqual(items[1]["published"], datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc).timestamp())

    def test_hn_uses_discussion_when_url_missing(self):
        items = sources.parse_hn(fixture("hn.json"))
        self.assertEqual(items[0]["score"], 420)
        self.assertEqual(items[0]["commentsUrl"], "https://news.ycombinator.com/item?id=1")
        self.assertEqual(items[1]["url"], "https://news.ycombinator.com/item?id=2")

    def test_lobsters_and_hf(self):
        lob = sources.parse_lobsters(fixture("lobsters.json"))
        self.assertEqual(lob[1]["url"], "https://lobste.rs/s/y")
        paper = sources.parse_hf(fixture("hf.json"))[0]
        self.assertEqual(paper["url"], "https://huggingface.co/papers/2610.00001")
        self.assertEqual((paper["score"], paper["summary"]), (33, "Sintesi AI"))
        self.assertEqual(paper["published"], datetime(2026, 10, 16, tzinfo=timezone.utc).timestamp())

    def test_source_window_override(self):
        catalog = [{"id": "hf", "name": "HF", "kind": "hf", "area": "RICERCA", "url": "u", "windowHours": 72}]
        items, _ = sources.collect(catalog, NOW + 86400, fetcher=lambda url: fixture("hf.json"))
        self.assertEqual(len(items), 1)


class CollectTest(unittest.TestCase):
    def test_window_cap_and_failures(self):
        def fetcher(url):
            if "broken" in url:
                raise OSError("timeout")
            return fixture("rss.xml")
        catalog = [{"id": "a", "name": "A", "kind": "feed", "area": "AI", "url": "https://a/feed"},
                   {"id": "b", "name": "B", "kind": "feed", "area": "TECH", "url": "https://broken/feed"}]
        items, status = sources.collect(catalog, NOW, fetcher=fetcher)
        self.assertEqual([i["title"] for i in items], ["Nuovo modello & benchmark"])
        self.assertEqual((items[0]["source"], items[0]["area"]), ("A", "AI"))
        self.assertEqual(status[0], {"name": "A", "ok": True, "count": 1})
        self.assertFalse(status[1]["ok"])
        self.assertIn("timeout", status[1]["error"])

    def test_hn_url_gets_window_start(self):
        seen = []

        def fetcher(url):
            seen.append(url)
            return json.dumps({"hits": []})
        sources.collect([{"id": "hn", "name": "HN", "kind": "hn", "area": "TECH", "url": sources.HN_URL}], NOW, fetcher=fetcher)
        self.assertIn("created_at_i>%d" % int(NOW - sources.WINDOW_HOURS * 3600), seen[0])

import json
import time
from datetime import datetime
from unittest import mock

from news_panel import edition
from tests.helpers import TempHomeCase

NOW = datetime(2026, 10, 17, 9, 0).timestamp()


def item(n, score=None, source="HN"):
    return {"title": "Notizia %d" % n, "url": "https://ex.com/%d" % n, "source": source, "area": "AI",
            "score": score, "published": NOW - n * 60, "summary": "s%d" % n, "commentsUrl": None}


ANSWER = {"headline": "Giornata di modelli", "topics": [
    {"title": "Nuovi modelli", "summary": "Due rilasci.", "area": "LLM", "heat": 9, "itemIds": ["n1", "n2", "x99"]},
    {"title": "Solo id falsi", "summary": "-", "area": "TECH", "heat": 2, "itemIds": ["x1"]}],
    "picks": [{"itemId": "n3", "why": "Da leggere"}, {"itemId": "nope", "why": "-"}]}


class SummarizeTest(TempHomeCase):
    def test_ids_are_validated_and_heat_clamped(self):
        prompts = []

        def runner(prompt):
            prompts.append(prompt)
            return ANSWER
        result = edition.summarize([item(1, 300), item(2), item(3, 10)], runner)
        self.assertIn("n1 | HN | 300 | Notizia 1", prompts[0])
        self.assertEqual(result["headline"], "Giornata di modelli")
        self.assertEqual(len(result["topics"]), 1)
        topic = result["topics"][0]
        self.assertEqual(topic["heat"], 5)
        self.assertEqual([i["title"] for i in topic["items"]], ["Notizia 1", "Notizia 2"])
        self.assertEqual(result["picks"], [dict(item(3, 10), why="Da leggere")])

    def test_fallback_without_claude(self):
        def runner(prompt):
            raise edition.EditionError("non disponibile")
        result = edition.summarize([item(1, 5), item(2, 50), item(3)], runner)
        self.assertEqual(result["topics"], [])
        self.assertEqual([p["title"] for p in result["picks"]], ["Notizia 2", "Notizia 1", "Notizia 3"])
        self.assertIn("non disponibile", result["error"])


class ShowTest(TempHomeCase):
    def write(self, edition_date):
        target = self.home / ".claude/news-panel/news.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"edition": edition_date, "topics": []}))

    def test_missing_edition_spawns_fetch_after_seven(self):
        data = edition.show(now=NOW)
        self.assertTrue(data["fetching"])
        self.spawned.assert_called_once()

    def test_today_edition_does_not_refetch(self):
        self.write("2026-10-17")
        data = edition.show(now=NOW)
        self.assertEqual(data["edition"], "2026-10-17")
        self.spawned.assert_not_called()

    def test_yesterday_waits_until_seven(self):
        self.write("2026-10-16")
        edition.show(now=datetime(2026, 10, 17, 6, 30).timestamp())
        self.spawned.assert_not_called()
        edition.show(now=NOW)
        self.spawned.assert_called_once()

    def test_failed_attempt_is_retried_after_an_hour(self):
        target = self.home / ".claude/news-panel/news.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"edition": "2026-10-16", "attemptedAt": NOW - 600}))
        edition.show(now=NOW)
        self.spawned.assert_not_called()
        edition.show(now=NOW + 3600)
        self.spawned.assert_called_once()

    def test_running_fetch_is_not_duplicated(self):
        lock = self.home / ".claude/news-panel/fetch.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(str(time.time()))
        self.assertTrue(edition.show(now=NOW)["fetching"])
        self.spawned.assert_not_called()


class RunTest(TempHomeCase):
    def test_writes_edition_and_releases_lock(self):
        catalog_items = [item(1, 300), item(2), item(3, 10)]
        status = [{"name": "HN", "ok": True, "count": 3}]
        result = edition.run(collector=lambda now: (catalog_items, status), runner=lambda p: ANSWER, now=NOW)
        saved = json.loads((self.home / ".claude/news-panel/news.json").read_text())
        self.assertEqual(saved, result)
        self.assertEqual((saved["edition"], saved["count"]), ("2026-10-17", 3))
        self.assertEqual(saved["sources"], status)
        self.assertFalse((self.home / ".claude/news-panel/fetch.lock").exists())

    def test_no_news_keeps_previous_edition(self):
        target = self.home / ".claude/news-panel/news.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"edition": "2026-10-16", "topics": [{"title": "ieri"}]}))
        edition.run(collector=lambda now: ([], [{"name": "HN", "ok": False, "count": 0, "error": "rete"}]),
                    runner=lambda p: ANSWER, now=NOW)
        saved = json.loads(target.read_text())
        self.assertEqual(saved["edition"], "2026-10-16")
        self.assertIn("rete", saved["error"])


class ClaudeRunnerTest(TempHomeCase):
    def run_claude(self):
        completed = mock.Mock(returncode=0, stderr="", stdout=json.dumps({"structured_output": {"headline": "ok"}}))
        with mock.patch("news_panel.edition.subprocess.run", return_value=completed) as run:
            self.assertEqual(edition.claude_runner("prompt"), {"headline": "ok"})
        return run.call_args.kwargs["input"]

    def test_prompt_is_unchanged_without_work_item(self):
        self.assertEqual(self.run_claude(), "prompt")

    def test_work_item_is_declared_in_the_prompt(self):
        target = self.home / ".claude/news-panel/work-item"
        target.parent.mkdir(parents=True)
        target.write_text("  AI-1\n")
        self.assertEqual(self.run_claude(), "Work-item: AI-1\n\nprompt")

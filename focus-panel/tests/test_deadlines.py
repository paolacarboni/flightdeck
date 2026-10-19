import json
import time

from focus_panel import deadlines, store
from tests.helpers import NOW, TempHomeCase

JIRA = [{"key": "OPS-412", "title": "Consegna HLD", "due": "2026-10-18", "url": "https://j/browse/OPS-412"},
        {"key": "OPS-400", "title": "Scaduto", "due": "2026-10-15", "url": "https://j/browse/OPS-400"}]


class SyncTest(TempHomeCase):
    def test_sync_writes_cache(self):
        deadlines.sync(fetcher=lambda: JIRA, now=NOW)
        cache = deadlines.load_cache()
        self.assertEqual(cache["items"], JIRA)
        self.assertEqual(cache["syncedAt"], NOW)
        self.assertIsNone(cache["error"])

    def test_failed_sync_keeps_previous_items(self):
        deadlines.sync(fetcher=lambda: JIRA, now=NOW)

        def broken():
            raise deadlines.DeadlineError("Jira non raggiungibile")
        deadlines.sync(fetcher=broken, now=NOW + 3600)
        cache = deadlines.load_cache()
        self.assertEqual(cache["items"], JIRA)
        self.assertEqual(cache["error"], "Jira non raggiungibile")
        self.assertEqual(cache["attemptedAt"], NOW + 3600)


class CollectTest(TempHomeCase):
    def test_merges_local_and_jira_sorted_within_a_week(self):
        deadlines.sync(fetcher=lambda: JIRA, now=NOW)
        state = store.load(NOW)
        store.add(state, "Demo sprint", 30, "dopo", due="2026-10-21", now=NOW)
        store.add(state, "Lontana", 30, "dopo", due="2026-11-30", now=NOW)
        finished = store.add(state, "Fatta", 30, "dopo", due="2026-10-19", now=NOW)
        finished["doneAt"] = NOW
        result = deadlines.collect(state, NOW)
        self.assertEqual([(d["title"], d["days"], d["source"]) for d in result["deadlines"]],
                         [("Scaduto", -2, "jira"), ("Consegna HLD", 1, "jira"), ("Demo sprint", 4, "local")])
        self.assertFalse(result["syncing"])
        self.spawned.assert_not_called()

    def test_stale_cache_spawns_sync_once(self):
        result = deadlines.collect(store.load(NOW), NOW)
        self.assertTrue(result["syncing"])
        self.spawned.assert_called_once()
        deadlines.sync(fetcher=lambda: JIRA, now=NOW)
        deadlines.collect(store.load(NOW), NOW + 29 * 60)
        self.spawned.assert_called_once()
        deadlines.collect(store.load(NOW), NOW + 31 * 60)
        self.assertEqual(self.spawned.call_count, 2)

    def test_running_sync_is_not_duplicated(self):
        lock = store.data_dir() / "sync.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(str(time.time()))
        result = deadlines.collect(store.load(NOW), NOW)
        self.assertTrue(result["syncing"])
        self.spawned.assert_not_called()

    def test_jira_error_is_reported(self):
        target = store.data_dir() / "deadlines.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"items": [], "error": "token scaduto", "syncedAt": None, "attemptedAt": NOW}))
        self.assertEqual(deadlines.collect(store.load(NOW), NOW)["jiraError"], "token scaduto")


class JiraIssuesTest(TempHomeCase):
    def test_maps_issues(self):
        issues = [{"key": "OPS-1", "fields": {"summary": " Titolo ", "duedate": "2026-10-18"}}]
        self.assertEqual(deadlines.map_issues(issues, "https://j"),
                         [{"key": "OPS-1", "title": "Titolo", "due": "2026-10-18", "url": "https://j/browse/OPS-1"}])

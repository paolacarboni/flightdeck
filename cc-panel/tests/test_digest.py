import json
import time

from cc_panel import digest
from tests.helpers import TempHomeCase

NOW = 2_000_000_000


def session(sid, **overrides):
    base = {"sessionId": sid, "cwd": "/r/repo", "keys": set(), "title": None, "mtime": NOW - 3600,
            "prompts": 6, "firstPrompt": "fai x", "edits": 4, "commits": 0, "files": ["/r/repo/a.py"],
            "promptSample": ["fai x", "poi y"]}
    base.update(overrides)
    return base


CONTEXT = {"epics": [{"key": "OPS-1", "summary": "Epica Uno"}],
           "items": [{"key": "OPS-10", "summary": "Task dieci"}]}


class CandidatesTest(TempHomeCase):
    def test_rules(self):
        indexed = [session("work"), session("commit", edits=0, commits=1),
                   session("questions", edits=0), session("chatty", prompts=2),
                   session("old", mtime=NOW - 20 * 86400), session("titled", title="OPS-10 x"),
                   session("linked"), session("ignored")]
        found = digest.candidates(indexed, {"linked": "OPS-10"}, {"ignored"}, NOW)
        self.assertEqual([s["sessionId"] for s in found], ["work", "commit"])


class EvaluateTest(TempHomeCase):
    def test_prompt_contains_context_and_evidence(self):
        prompts = []

        def runner(prompt):
            prompts.append(prompt)
            return {"valuable": True, "title": "Fare x", "why": "fatto x", "existingKey": None, "epicKey": "OPS-1"}
        result = digest.evaluate(session("s"), CONTEXT, runner)
        self.assertEqual(result["title"], "Fare x")
        for part in ("OPS-1 Epica Uno", "OPS-10 Task dieci", "/r/repo/a.py", "fai x", "poi y", "repo"):
            self.assertIn(part, prompts[0])

    def run_digest(self, indexed, runner, now=NOW):
        board_cache = self.home / ".claude/cc-panel/board.json"
        board_cache.parent.mkdir(parents=True, exist_ok=True)
        board_cache.write_text(json.dumps({"epics": [{"key": "OPS-1", "summary": "Epica Uno", "items": [
            {"key": "OPS-10", "summary": "Task dieci"}]}], "noEpic": []}))
        return digest.run(indexed=indexed, runner=runner, now=now, workers=1)

    def test_results_are_cached(self):
        calls = []

        def runner(prompt):
            if "Valuta UNA sessione" not in prompt:
                return {"groups": []}
            calls.append(prompt)
            return {"valuable": True, "title": "T", "why": "w", "existingKey": None, "epicKey": None}
        self.run_digest([session("s")], runner)
        self.run_digest([session("s")], runner)
        self.assertEqual(len(calls), 1)
        self.assertEqual(digest.load()["s"]["result"]["title"], "T")

    def test_failures_are_retried_later(self):
        def broken(prompt):
            raise digest.DigestError("claude non disponibile")
        self.run_digest([session("s")], broken)
        self.assertNotIn("s", digest.load())

    def test_changed_session_reevaluated_only_after_cooldown(self):
        calls = []

        def runner(prompt):
            if "Valuta UNA sessione" not in prompt:
                return {"groups": []}
            calls.append(prompt)
            return {"valuable": False, "title": "T", "why": "w", "existingKey": None, "epicKey": None}
        self.run_digest([session("s", mtime=NOW - 100)], runner, now=NOW)
        self.run_digest([session("s", mtime=NOW - 50)], runner, now=NOW + 3600)
        self.assertEqual(len(calls), 1)
        self.run_digest([session("s", mtime=NOW - 50)], runner, now=NOW + 7 * 3600)
        self.assertEqual(len(calls), 2)

    def test_active_lock_prevents_second_run_and_stale_lock_is_ignored(self):
        lock = self.home / ".claude/cc-panel/digest.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(time.time()))
        calls = []
        runner = lambda prompt: calls.append(prompt) or {"valuable": False, "title": "", "why": "", "existingKey": None, "epicKey": None}
        self.run_digest([session("s")], runner)
        self.assertEqual(calls, [])
        lock.write_text(str(time.time() - 3600))
        self.run_digest([session("s")], runner)
        self.assertEqual(len(calls), 1)
        self.assertFalse(lock.exists())

    def test_pending_lists_unevaluated_candidates(self):
        self.assertEqual(digest.pending([session("a")], {}, set(), NOW), 1)

    def test_each_result_is_saved_as_soon_as_ready(self):
        seen = []

        def runner(prompt):
            if "Valuta UNA sessione" not in prompt:
                return {"groups": []}
            # Alla seconda valutazione la prima deve essere già su disco.
            seen.append(set(digest.load()))
            return {"valuable": True, "title": "T", "why": "w", "existingKey": None, "epicKey": None}
        self.run_digest([session("a", mtime=NOW - 10), session("b", mtime=NOW - 20)], runner)
        self.assertEqual(len(seen), 2)
        self.assertEqual(len(seen[1]), 1)


class GroupingTest(EvaluateTest):
    def evaluation(self, existing=None, epic=None, valuable=True, title="T"):
        return {"valuable": valuable, "title": title, "why": "w", "existingKey": existing, "epicKey": epic}

    def test_existing_ticket_is_linked_automatically(self):
        from cc_panel import tracking
        self.run_digest([session("s")], lambda prompt: self.evaluation(existing="OPS-10")
                        if "Valuta UNA sessione" in prompt else {"groups": []})
        self.assertEqual(tracking.links(), {"s": "OPS-10"})

    def test_unknown_existing_key_is_not_linked(self):
        from cc_panel import tracking
        self.run_digest([session("s")], lambda prompt: self.evaluation(existing="ZZ-9")
                        if "Valuta UNA sessione" in prompt else {"groups": []})
        self.assertEqual(tracking.links(), {})

    def test_groups_built_once_per_input(self):
        grouping_calls = []

        def runner(prompt):
            if "Valuta UNA sessione" in prompt:
                return self.evaluation(title="lavoro %s" % ("a" if "fai a" in prompt else "b"))
            grouping_calls.append(prompt)
            return {"groups": [{"title": "Tema", "why": "perché", "epicKey": "OPS-1", "sessionIds": ["a", "b", "zz"]}]}
        sessions_ = [session("a", promptSample=["fai a"]), session("b", promptSample=["fai b"])]
        self.run_digest(sessions_, runner)
        self.run_digest(sessions_, runner)
        self.assertEqual(len(grouping_calls), 1)
        self.assertIn("lavoro a", grouping_calls[0])
        [group] = digest.groups()
        self.assertEqual(group["sessionIds"], ["a", "b"])

    def test_pending_counts_stale_grouping(self):
        self.run_digest([session("a")], lambda prompt: self.evaluation()
                        if "Valuta UNA sessione" in prompt else {"groups": []})
        self.assertEqual(digest.pending([session("a")], {}, set(), NOW), 0)
        digest._save_groups({"inputHash": "diverso", "groups": []})
        self.assertEqual(digest.pending([session("a")], {}, set(), NOW), 1)

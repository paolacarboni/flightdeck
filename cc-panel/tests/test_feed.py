from datetime import datetime, timedelta

from cc_panel import feed, paths
from tests.helpers import TempHomeCase

NOW = datetime(2026, 10, 19, 22, 0, 0)


def hook(name, session="s1", **extra):
    payload = {"hook_event_name": name, "session_id": session, "cwd": "/r/%s" % session}
    payload.update(extra)
    return payload


class RecordHookTest(TempHomeCase):
    def test_maps_hook_events_to_kinds(self):
        cases = [("SessionStart", "start"), ("UserPromptSubmit", "prompt"), ("Notification", "attention"),
                 ("Stop", "idle"), ("SessionEnd", "end")]
        for name, kind in cases:
            self.assertEqual(feed.record_hook(hook(name), NOW)["kind"], kind)
        self.assertEqual([e["kind"] for e in feed.load()], [k for _, k in cases])

    def test_exit_plan_mode_is_a_plan_event_other_tools_are_ignored(self):
        self.assertEqual(feed.record_hook(hook("PostToolUse", tool_name="ExitPlanMode"), NOW)["kind"], "plan")
        self.assertIsNone(feed.record_hook(hook("PostToolUse", tool_name="Bash"), NOW))
        self.assertEqual(len(feed.load()), 1)

    def test_prompt_text_is_truncated_and_notification_keeps_message(self):
        prompt = feed.record_hook(hook("UserPromptSubmit", prompt="x" * 500), NOW)
        self.assertEqual(len(prompt["text"]), 200)
        attention = feed.record_hook(hook("Notification", message="Claude needs your permission"), NOW)
        self.assertEqual(attention["text"], "Claude needs your permission")

    def test_payload_without_session_is_ignored(self):
        self.assertIsNone(feed.record_hook({"hook_event_name": "Stop"}, NOW))
        self.assertIsNone(feed.record_hook("non un dizionario", NOW))
        self.assertFalse(paths.events_file().exists())

    def test_record_has_timestamp_session_and_cwd(self):
        event = feed.record_hook(hook("Stop", session="abc"), NOW)
        self.assertEqual(event, {"ts": "2026-10-19T22:00:00", "session": "abc", "cwd": "/r/abc", "kind": "idle"})


class DecideTest(TempHomeCase):
    def test_decision_is_recorded_with_short_id(self):
        record = feed.decide("s1", "/r", "Cache Redis", why="latenza", alternatives=["in-memory"],
                             watch="invalidazione", learn="cache-aside", now=NOW)
        self.assertRegex(record["id"], r"^[0-9a-f]{6}$")
        self.assertEqual(feed.load(), [record])
        self.assertEqual(record["alternatives"], ["in-memory"])
        self.assertEqual(record["kind"], "decision")

    def test_optional_fields_are_omitted_when_empty(self):
        record = feed.decide("s1", "/r", "Solo titolo", now=NOW)
        self.assertNotIn("watch", record)
        self.assertNotIn("alternatives", record)


class LoadTest(TempHomeCase):
    def test_corrupt_lines_are_skipped(self):
        feed.record_hook(hook("Stop"), NOW)
        with paths.events_file().open("a", encoding="utf-8") as out:
            out.write("{rotto\n[1, 2]\n\n")
        feed.record_hook(hook("SessionEnd"), NOW)
        self.assertEqual([e["kind"] for e in feed.load()], ["idle", "end"])

    def test_missing_file_is_empty(self):
        self.assertEqual(feed.load(), [])


class BuildTest(TempHomeCase):
    def event(self, session, kind, minutes_ago, **extra):
        event = {"ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds"),
                 "session": session, "cwd": "/r/%s" % session, "kind": kind}
        event.update(extra)
        return event

    def test_session_status_comes_from_last_event(self):
        events = [self.event("a", "prompt", 10, text="fai X"), self.event("b", "prompt", 9),
                  self.event("b", "attention", 8, text="permesso"), self.event("c", "start", 7),
                  self.event("c", "idle", 6), self.event("a", "plan", 5)]
        sessions = {s["session"]: s for s in feed.build(events, NOW)["sessions"]}
        self.assertEqual(sessions["a"]["status"], "working")
        self.assertEqual(sessions["a"]["prompt"], "fai X")
        self.assertEqual(sessions["b"]["status"], "waiting")
        self.assertEqual(sessions["c"]["status"], "idle")

    def test_decision_keeps_status_and_counts(self):
        events = [self.event("a", "prompt", 10), self.event("a", "decision", 5, id="d1", title="T")]
        session = feed.build(events, NOW)["sessions"][0]
        self.assertEqual(session["status"], "working")
        self.assertEqual(session["decisions"], 1)

    def test_ended_and_stale_sessions_are_not_listed(self):
        events = [self.event("a", "prompt", 10), self.event("a", "end", 5),
                  self.event("b", "prompt", 25 * 60), self.event("c", "idle", 60)]
        self.assertEqual([s["session"] for s in feed.build(events, NOW)["sessions"]], ["c"])

    def test_decisions_newest_first_and_attention_list(self):
        events = [self.event("a", "decision", 30, id="d1", title="Vecchia"),
                  self.event("a", "decision", 10, id="d2", title="Nuova", watch="migrazione dati"),
                  self.event("b", "attention", 5, text="permesso Bash")]
        model = feed.build(events, NOW)
        self.assertEqual([d["id"] for d in model["decisions"]], ["d2", "d1"])
        self.assertEqual([(a["session"], a["text"]) for a in model["attention"]],
                         [("b", "permesso Bash"), ("a", "migrazione dati")])

    def test_render_text_shows_sessions_decisions_and_learn(self):
        events = [self.event("a", "prompt", 10, text="fai X"),
                  self.event("a", "decision", 5, id="d1", title="Cache Redis", why="latenza",
                             alternatives=["in-memory"], learn="cache-aside")]
        text = feed.render_text(feed.build(events, NOW))
        for expected in ("working", "fai X", "Cache Redis", "latenza", "in-memory", "cache-aside", "dive d1"):
            self.assertIn(expected, text)

    def test_dive_prompt_uses_learn_or_decision(self):
        with_learn = feed.dive_prompt({"title": "Cache Redis", "learn": "cache-aside"})
        self.assertIn("cache-aside", with_learn)
        self.assertIn("Cache Redis", with_learn)
        self.assertIn("Cache Redis", feed.dive_prompt({"title": "Cache Redis"}))

import unittest
from datetime import datetime, timedelta

from cc_panel import feed, menubar

NOW = datetime(2026, 10, 20, 12, 0, 0)
HOME = "/Users/me"
CMD = "/x/bin/cc-panel"


def event(session, kind, minutes_ago, cwd="/r/proj", **extra):
    record = {"ts": (NOW - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds"),
              "session": session, "cwd": cwd, "kind": kind}
    record.update(extra)
    return record


def render(events):
    return menubar.render(feed.build(events, NOW), NOW, CMD, home=HOME)


class TitleTest(unittest.TestCase):
    def test_waiting_wins_over_working(self):
        lines = render([event("a", "prompt", 1, text="x"), event("b", "attention", 1, text="ok?")])
        self.assertTrue(lines[0].startswith("⏸ 1"))
        self.assertIn("color=", lines[0])

    def test_working_count_and_quiet_state(self):
        self.assertTrue(render([event("a", "prompt", 1, text="x")])[0].startswith("● 1"))
        self.assertTrue(render([event("a", "idle", 1)])[0].startswith("○"))
        self.assertEqual(lines_after_title(render([])), ["Nessuna sessione attiva | color=%s" % menubar.DIM])


def lines_after_title(lines):
    return [line for line in lines[1:] if line != "---" and not line.startswith("Sessioni")]


class SessionsTest(unittest.TestCase):
    def test_active_sessions_show_label_and_prompt_idle_are_folded(self):
        lines = render([event("a", "prompt", 1, text="sistema il feed"), event("b", "idle", 2, cwd=HOME),
                        event("c", "idle", 3)])
        top = [line for line in lines if not line.startswith("--")]
        self.assertTrue(any("proj" in line and "sistema il feed" in line for line in top))
        self.assertIn("2 inattive", "\n".join(top))
        self.assertTrue(any(line.startswith("--~") for line in lines))

    def test_waiting_session_says_it_is_waiting(self):
        lines = render([event("a", "attention", 1, text="Claude is waiting for your input")])
        self.assertTrue(any(line.startswith("⏸ proj") and "ti aspetta" in line for line in lines))

    def test_text_is_safe_for_xbar(self):
        lines = render([event("a", "prompt", 1, text="--a | b\nc " + "y" * 200)])
        prompt_line = next(line for line in lines if line.startswith("● proj"))
        text = prompt_line.split(" | ")[0]
        self.assertNotIn("\n", prompt_line)
        self.assertLessEqual(len(text), 70)
        self.assertIn("a ¦ b c", text)


class DecisionsTest(unittest.TestCase):
    def test_only_today_titles_on_top_details_in_submenu(self):
        lines = render([event("a", "decision", 30, id="d1", title="Cache Redis", why="latenza",
                              alternatives=["in-memory"], watch="memoria", learn="cache-aside"),
                        event("a", "decision", 60 * 13, id="d0", title="Di ieri")])
        top = [line for line in lines if not line.startswith("--")]
        self.assertTrue(any(line.startswith("Cache Redis") for line in top))
        self.assertFalse(any("Di ieri" in line for line in top))
        sub = "\n".join(line for line in lines if line.startswith("--"))
        for expected in ("latenza", "in-memory", "memoria", "Di ieri"):
            self.assertIn(expected, sub)
        dive = next(line for line in lines if "cache-aside" in line)
        self.assertIn("shell=%s" % CMD, dive)
        self.assertIn("param1=dive param2=d1", dive)

    def test_today_list_is_capped(self):
        events = [event("a", "decision", i, id="d%d" % i, title="Decisione %d" % i) for i in range(10)]
        top = [line for line in render(events) if line.startswith("Decisione")]
        self.assertEqual(len(top), menubar.TODAY_DECISIONS)
        self.assertTrue(any(line.startswith("Altre 4") for line in render(events)))

    def test_long_reason_is_wrapped_on_several_lines(self):
        lines = render([event("a", "decision", 1, id="d1", title="T", why="parola " * 40)])
        why = [line for line in lines if line.startswith("--") and "parola" in line]
        self.assertGreater(len(why), 1)
        self.assertTrue(all(len(line.split(" | ")[0]) <= menubar.WRAP + 2 for line in why))


if __name__ == "__main__":
    unittest.main()

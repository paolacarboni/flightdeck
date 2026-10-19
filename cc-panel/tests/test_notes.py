import io
import unittest
from unittest import mock

from cc_panel import cli, notes
from tests.helpers import TempHomeCase

NOTE = """---
type: jira
key: OPS-1
---
%% managed:jira %%
# OPS-1 · Titolo
%% /managed:jira %%

## Note

mie note
"""


class AddEntryTest(unittest.TestCase):
    def test_creates_section_after_existing_text(self):
        text = notes.add_entry(NOTE, "Prossimo passo: test", "2026-10-17 10:00")
        self.assertTrue(text.startswith(NOTE))
        self.assertIn("## Ripresa\n\n### 2026-10-17 10:00\n\nProssimo passo: test\n", text)

    def test_newest_entry_goes_first(self):
        text = notes.add_entry(NOTE, "primo", "2026-10-17 10:00")
        text = notes.add_entry(text, "secondo", "2026-10-18 09:00")
        self.assertLess(text.index("secondo"), text.index("primo"))
        self.assertTrue(text.startswith(NOTE))

    def test_latest_entries_returns_most_recent_first(self):
        text = NOTE
        for stamp, body in (("2026-10-01 10:00", "uno"), ("2026-10-02 10:00", "due"), ("2026-10-03 10:00", "tre")):
            text = notes.add_entry(text, body, stamp)
        entries = notes.latest_entries(text, 2)
        self.assertEqual(len(entries), 2)
        self.assertIn("2026-10-03 10:00", entries[0])
        self.assertIn("tre", entries[0])
        self.assertIn("due", entries[1])

    def test_latest_entries_empty_without_section(self):
        self.assertEqual(notes.latest_entries(NOTE, 2), [])

    def test_section_followed_by_other_heading_is_bounded(self):
        text = notes.add_entry(NOTE, "uno", "2026-10-01 10:00") + "\n## Altro\n\nnon è ripresa\n"
        self.assertNotIn("non è ripresa", notes.latest_entries(text, 2)[0])


class ParkCommandTest(TempHomeCase):
    def run_park(self, stdin):
        with mock.patch("sys.stdin", io.StringIO(stdin)), mock.patch("sys.stderr", io.StringIO()) as err:
            code = cli.main(["park", "OPS-7"])
        return code, err.getvalue()

    def test_park_creates_missing_note(self):
        code, _ = self.run_park("**Prossimo passo:** x\n")
        note = (self.vault / "Jira/OPS-7.md").read_text()
        self.assertEqual(code, 0)
        self.assertIn("key: OPS-7", note)
        self.assertIn("## Note", note)
        self.assertIn("**Prossimo passo:** x", note)

    def test_park_rejects_empty_input(self):
        code, err = self.run_park("  \n")
        self.assertEqual(code, 1)
        self.assertIn("vuota", err)
        self.assertFalse((self.vault / "Jira/OPS-7.md").exists())

    def test_park_rejects_invalid_key(self):
        with mock.patch("sys.stdin", io.StringIO("x")), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(cli.main(["park", "ai-7"]), 1)


class NextStepTest(unittest.TestCase):
    def test_next_step_from_latest_entry(self):
        text = notes.add_entry(NOTE, "**Prossimo passo:** vecchio", "2026-10-01 10:00")
        text = notes.add_entry(text, "**Fatto:** x\n**Prossimo passo:** scrivere i test", "2026-10-02 10:00")
        self.assertEqual(notes.next_step(text), "scrivere i test")

    def test_none_without_resume_or_line(self):
        self.assertIsNone(notes.next_step(NOTE))
        self.assertIsNone(notes.next_step(notes.add_entry(NOTE, "**Fatto:** x", "2026-10-01 10:00")))

    def test_list_item_prefix_is_accepted(self):
        text = notes.add_entry(NOTE, "- **Prossimo passo:** aprire la PR", "2026-10-01 10:00")
        self.assertEqual(notes.next_step(text), "aprire la PR")

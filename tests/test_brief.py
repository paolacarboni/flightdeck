import unittest

from cc_panel import brief

ISSUE = {"key": "AI-9", "summary": "Titolo", "status": "IN LAVORAZIONE", "type": "Task",
         "epic": "AI-1", "epic_summary": "Epica", "description": "Descrizione breve",
         "comments": [{"author": "A", "created": "2026-10-05T10:00", "body": "ok"}],
         "url": "https://example.atlassian.net/browse/AI-9"}


class BriefTest(unittest.TestCase):
    def test_first_line_names_ticket(self):
        self.assertEqual(brief.compose(ISSUE, []).splitlines()[0], "Ticket: AI-9 — Titolo")

    def test_contains_ticket_sections_and_closing(self):
        text = brief.compose(ISSUE, [])
        for part in ("## Ticket", "AI-1 Epica", ISSUE["url"], "## Descrizione", "## Commenti recenti", "/park"):
            self.assertIn(part, text)
        self.assertNotIn("## Ultima ripresa", text)

    def test_resume_entries_included(self):
        text = brief.compose(ISSUE, ["### 2026-10-17 10:00\n\n**Prossimo passo:** x"])
        self.assertIn("## Ultima ripresa", text)
        self.assertIn("**Prossimo passo:** x", text)

    def test_empty_sections_omitted(self):
        issue = dict(ISSUE, description="", comments=[], epic=None, epic_summary=None)
        text = brief.compose(issue, [])
        self.assertNotIn("## Descrizione", text)
        self.assertNotIn("## Commenti recenti", text)
        self.assertNotIn("Epica:", text)

    def test_long_description_truncated(self):
        text = brief.compose(dict(ISSUE, description="x" * 5000), [])
        self.assertIn("x" * 4000 + " [troncato]", text)
        self.assertNotIn("x" * 4001, text)

    def test_long_comment_truncated(self):
        issue = dict(ISSUE, comments=[{"author": "A", "created": "2026-10-05", "body": "y" * 900}])
        self.assertIn("y" * 800 + " [troncato]", brief.compose(issue, []))

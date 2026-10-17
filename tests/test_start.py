import io
import json
import subprocess
from unittest import mock

from cc_panel import folders, jira, start, terminal
from tests.helpers import TempHomeCase

ISSUE = {"key": "AI-9", "summary": "Titolo " + "parola " * 7 + "lunghissima (Fase 2)", "status": "Backlog", "type": "Task", "epic": None,
         "epic_summary": None, "description": "", "comments": [], "url": "u"}


class StartTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.repo = self.home / "Projects/r"
        (self.repo / ".git").mkdir(parents=True)
        self.other = self.home / "Projects/s"
        (self.other / ".git").mkdir(parents=True)
        self.launched = []
        self.out = io.StringIO()

    def run_start(self, answers=("",), issue=ISSUE, **kwargs):
        replies = iter(answers)
        with mock.patch("cc_panel.jira.issue", side_effect=issue if isinstance(issue, Exception) else None,
                        return_value=issue), mock.patch("sys.stderr", io.StringIO()) as err:
            code = start.run("AI-9", ask=lambda _prompt: next(replies), launch=self.launched.append,
                             out=self.out, **kwargs)
        self.err = err.getvalue()
        return code

    def open_session(self):
        path = self.home / ".claude/sessions/1.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"sessionId": "sid", "name": "AI-9 x", "cwd": str(self.repo), "status": "idle"}))

    def test_open_session_is_resumed_without_jira(self):
        self.open_session()
        with mock.patch("cc_panel.jira.issue") as issue:
            code = start.run("AI-9", ask=None, launch=self.launched.append, out=self.out)
        issue.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("claude --ide --resume sid", self.launched[0])

    def test_new_flag_ignores_open_session(self):
        self.open_session()
        self.assertEqual(self.run_start(new=True), 0)
        self.assertIn("--name", self.launched[0])

    def test_empty_answer_picks_first_proposal_and_remembers_it(self):
        self.assertEqual(self.run_start(("",)), 0)
        self.assertIn("cd %s &&" % self.repo, self.launched[0])
        self.assertEqual(folders.remembered("AI-9"), self.repo)

    def test_number_and_path_answers(self):
        self.run_start(("2",))
        self.assertIn("cd %s &&" % self.other, self.launched[-1])
        self.run_start((str(self.repo),))
        self.assertIn("cd %s &&" % self.repo, self.launched[-1])

    def test_invalid_answer_asks_again(self):
        self.run_start(("99", "/non/esiste", "1"))
        self.assertEqual(len(self.launched), 1)

    def test_dir_option_skips_prompt(self):
        self.assertEqual(self.run_start((), dir_=str(self.other)), 0)
        self.assertIn("cd %s &&" % self.other, self.launched[0])

    def test_brief_saved_and_name_truncated(self):
        self.run_start(("",))
        brief_file = self.home / ".claude/cc-panel/briefs/AI-9.md"
        self.assertTrue(brief_file.read_text().startswith("Ticket: AI-9"))
        # «Titolo » + 7 × «parola » = 56 caratteri; «lunghissima» sfora i 60: si taglia all'ultima parola intera.
        self.assertIn("--name 'AI-9 Titolo%s'" % (" parola" * 7), self.launched[0])

    def test_resume_entries_from_note_in_brief(self):
        note = self.vault / "Jira/AI-9.md"
        note.parent.mkdir(parents=True)
        note.write_text("## Note\n\n## Ripresa\n\n### 2026-10-17 10:00\n\n**Prossimo passo:** y\n")
        self.run_start(("",))
        self.assertIn("**Prossimo passo:** y", (self.home / ".claude/cc-panel/briefs/AI-9.md").read_text())

    def test_jira_error_exits_without_window(self):
        self.assertEqual(self.run_start(issue=jira.JiraError("Jira non raggiungibile")), 1)
        self.assertEqual(self.launched, [])
        self.assertIn("Jira non raggiungibile", self.err)

    def test_non_interactive_without_dir_explains_dir_option(self):
        def no_tty(_prompt):
            raise EOFError
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE), mock.patch("sys.stderr", io.StringIO()) as err:
            code = start.run("AI-9", ask=no_tty, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 1)
        self.assertIn("--dir", err.getvalue())
        self.assertEqual(self.launched, [])

    def test_non_interactive_uses_remembered_folder(self):
        folders.remember("AI-9", self.other)

        def no_tty(_prompt):
            raise EOFError
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE):
            code = start.run("AI-9", ask=no_tty, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 0)
        self.assertIn("cd %s &&" % self.other, self.launched[0])

    def closed_transcript(self):
        path = self.home / ".claude/projects/p/closed-id.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"type": "user", "cwd": str(self.other), "message": {"content": "x"}}) + "\n"
                        + json.dumps({"type": "custom-title", "customTitle": "AI-9 vecchia"}) + "\n")

    def test_closed_session_is_resumed_without_jira(self):
        self.closed_transcript()
        with mock.patch("cc_panel.jira.issue") as issue:
            code = start.run("AI-9", ask=None, launch=self.launched.append, out=self.out)
        issue.assert_not_called()
        self.assertEqual(code, 0)
        self.assertEqual(self.launched[0], "cd %s && claude --ide --resume closed-id" % self.other)

    def test_new_flag_ignores_closed_session(self):
        self.closed_transcript()
        self.run_start(new=True)
        self.assertIn("--name", self.launched[0])

    def test_session_name_drops_dangling_parenthesis(self):
        self.assertEqual(start.session_name("OPS-410", "[Follow-up] Aggiornare i permessi del gruppo amministratori (Fase 2)"),
                         "OPS-410 [Follow-up] Aggiornare i permessi del gruppo amministratori")
        self.assertEqual(start.session_name("AI-1", "Breve"), "AI-1 Breve")

    def test_auto_picks_first_proposal_without_asking(self):
        def never(_prompt):
            raise AssertionError("non deve chiedere")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE):
            code = start.run("AI-9", auto=True, ask=never, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 0)
        self.assertIn("cd %s &&" % self.repo, self.launched[0])

    def test_auto_without_proposals_fails(self):
        import shutil
        shutil.rmtree(self.home / "Projects")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE), mock.patch("sys.stderr", io.StringIO()):
            code = start.run("AI-9", auto=True, ask=None, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 1)
        self.assertEqual(self.launched, [])

    def test_terminal_launch_failure_explains_automation_permission(self):
        def denied(_command):
            raise terminal.LaunchError("Ghostty")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE), mock.patch("sys.stderr", io.StringIO()) as err:
            code = start.run("AI-9", dir_=str(self.repo), launch=denied, out=self.out)
        self.assertEqual(code, 1)
        self.assertIn("Automazione", err.getvalue())

    def test_start_never_opens_an_editor(self):
        self.assertFalse(hasattr(terminal, "open_editor"))
        self.run_start(("",))
        self.assertEqual(len(self.launched), 1)

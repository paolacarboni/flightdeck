import io
import json
import shutil
import subprocess
from unittest import mock

from cc_panel import folders, jira, start, terminal
from tests.helpers import TempHomeCase

ISSUE = {"key": "OPS-9", "summary": "Titolo " + "parola " * 7 + "lunghissima (Fase 2)", "status": "Backlog", "type": "Task", "epic": None,
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
            code = start.run("OPS-9", ask=lambda _prompt: next(replies), launch=self.launched.append,
                             out=self.out, **kwargs)
        self.err = err.getvalue()
        return code

    def open_session(self):
        path = self.home / ".claude/sessions/1.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"sessionId": "sid", "name": "OPS-9 x", "cwd": str(self.repo), "status": "idle"}))

    def test_open_session_is_resumed_without_jira(self):
        self.open_session()
        with mock.patch("cc_panel.jira.issue") as issue:
            code = start.run("OPS-9", ask=None, launch=self.launched.append, out=self.out)
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
        self.assertEqual(folders.remembered("OPS-9"), self.repo)

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
        brief_file = self.home / ".claude/cc-panel/briefs/OPS-9.md"
        self.assertTrue(brief_file.read_text().startswith("Ticket: OPS-9"))
        # «Titolo » + 7 × «parola » = 56 caratteri; «lunghissima» sfora i 60: si taglia all'ultima parola intera.
        self.assertIn("--name 'OPS-9 Titolo%s'" % (" parola" * 7), self.launched[0])

    def test_resume_entries_from_note_in_brief(self):
        note = self.vault / "Jira/OPS-9.md"
        note.parent.mkdir(parents=True)
        note.write_text("## Note\n\n## Ripresa\n\n### 2026-10-17 10:00\n\n**Prossimo passo:** y\n")
        self.run_start(("",))
        self.assertIn("**Prossimo passo:** y", (self.home / ".claude/cc-panel/briefs/OPS-9.md").read_text())

    def test_jira_error_exits_without_window(self):
        self.assertEqual(self.run_start(issue=jira.JiraError("Jira non raggiungibile")), 1)
        self.assertEqual(self.launched, [])
        self.assertIn("Jira non raggiungibile", self.err)

    def test_non_interactive_without_dir_explains_dir_option(self):
        def no_tty(_prompt):
            raise EOFError
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE), mock.patch("sys.stderr", io.StringIO()) as err:
            code = start.run("OPS-9", ask=no_tty, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 1)
        self.assertIn("--dir", err.getvalue())
        self.assertEqual(self.launched, [])

    def test_non_interactive_uses_remembered_folder(self):
        folders.remember("OPS-9", self.other)

        def no_tty(_prompt):
            raise EOFError
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE):
            code = start.run("OPS-9", ask=no_tty, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 0)
        self.assertIn("cd %s &&" % self.other, self.launched[0])

    def closed_transcript(self):
        path = self.home / ".claude/projects/p/closed-id.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"type": "user", "cwd": str(self.other), "message": {"content": "x"}}) + "\n"
                        + json.dumps({"type": "custom-title", "customTitle": "OPS-9 vecchia"}) + "\n")

    def test_closed_session_is_resumed_without_jira(self):
        self.closed_transcript()
        with mock.patch("cc_panel.jira.issue") as issue:
            code = start.run("OPS-9", ask=None, launch=self.launched.append, out=self.out)
        issue.assert_not_called()
        self.assertEqual(code, 0)
        self.assertEqual(self.launched[0], "cd %s && claude --ide --resume closed-id" % self.other)

    def test_new_flag_ignores_closed_session(self):
        self.closed_transcript()
        self.run_start(new=True)
        self.assertIn("--name", self.launched[0])

    def test_session_name_drops_dangling_parenthesis(self):
        self.assertEqual(start.session_name("APP-410", "[Follow-up IT] Disaccoppiamento e adeguamento gruppo ADMIN (Fase 2)"),
                         "APP-410 [Follow-up IT] Disaccoppiamento e adeguamento gruppo ADMIN")
        self.assertEqual(start.session_name("OPS-1", "Breve"), "OPS-1 Breve")

    def test_auto_picks_first_proposal_without_asking(self):
        def never(_prompt):
            raise AssertionError("non deve chiedere")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE):
            code = start.run("OPS-9", auto=True, ask=never, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 0)
        self.assertIn("cd %s &&" % self.repo, self.launched[0])

    def test_auto_without_proposals_fails(self):
        import shutil
        shutil.rmtree(self.home / "Projects")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE), mock.patch("sys.stderr", io.StringIO()):
            code = start.run("OPS-9", auto=True, ask=None, launch=self.launched.append, out=self.out)
        self.assertEqual(code, 1)
        self.assertEqual(self.launched, [])

    def fake_rank(self, results, warning=None):
        self.ranked = []

        def rank(issue, warn, dense=None):
            self.ranked.append(issue["key"])
            self.dense = dense
            if warning:
                warn(warning)
            return results
        return rank

    def run_auto(self, results, warning=None):
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE):
            return start.run("OPS-9", auto=True, ask=None, launch=self.launched.append, out=self.out,
                             rank=self.fake_rank(results, warning))

    def test_new_ticket_lists_ranked_folders_first_and_auto_opens_the_first(self):
        results = [(self.other, "README: servizio s"), (self.repo, "nome citato nel ticket")]
        self.assertEqual(self.run_auto(results), 0)
        self.assertIn("cd %s &&" % self.other, self.launched[0])
        self.assertEqual(folders.remembered("OPS-9"), self.other)
        output = self.out.getvalue()
        self.assertRegex(output, r"Cartelle proposte dal ticket \(\d+,\d s\):")
        self.assertIn("   1) %s — README: servizio s" % self.other, output)
        self.assertIn("   2) %s — nome citato nel ticket" % self.repo, output)

    def test_known_ticket_skips_ranking(self):
        folders.remember("OPS-9", self.repo)
        self.run_auto([(self.other, "x")])
        self.assertEqual(self.ranked, [])
        self.assertIn("cd %s &&" % self.repo, self.launched[0])
        shutil.rmtree(self.home / ".claude/cc-panel")
        transcript = self.home / ".claude/projects/p/t.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "user", "cwd": str(self.repo), "message": {"content": "OPS-9"}}) + "\n")
        self.run_auto([(self.other, "x")])
        self.assertEqual(self.ranked, [])

    def test_no_ranking_keeps_current_order_and_shows_the_reason(self):
        self.assertEqual(self.run_auto([], "ricerca semantica non disponibile (x): uso solo le parole del ticket"), 0)
        self.assertEqual(self.ranked, ["OPS-9"])
        self.assertIn("cd %s &&" % self.repo, self.launched[0])
        self.assertIn("ricerca semantica non disponibile (x)", self.out.getvalue())
        self.assertNotIn("Cartelle proposte dal ticket", self.out.getvalue())

    def test_ranked_folder_is_listed_once_with_its_evidence(self):
        transcript = self.home / ".claude/projects/p/e.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "user", "cwd": str(self.other), "message": {"content": "OPS-1"}}) + "\n")
        with mock.patch("cc_panel.jira.issue", return_value=dict(ISSUE, epic="OPS-1")):
            start.run("OPS-9", ask=lambda _p: "", launch=self.launched.append, out=self.out,
                      rank=self.fake_rank([(self.other, "struttura")]))
        listed = [line for line in self.out.getvalue().splitlines() if line.startswith("   ")]
        self.assertEqual(listed, ["   1) %s — struttura" % self.other, "   2) %s" % self.repo])
        self.assertIn("cd %s &&" % self.other, self.launched[0])

    class Warm:
        def __init__(self, events):
            self.events, self.closed = events, False

        def __call__(self, text, timeout):
            return {}

        def close(self):
            self.closed = True

    def run_warm(self, issue=ISSUE, **kwargs):
        events = self.events = []
        self.warm = self.Warm(events)

        def warm_up():
            events.append("modello")
            return self.warm

        def fetch(key):
            events.append("jira")
            if isinstance(issue, Exception):
                raise issue
            return issue
        with mock.patch("cc_panel.jira.issue", side_effect=fetch), mock.patch("sys.stderr", io.StringIO()):
            code = start.run("OPS-9", auto=True, ask=None, launch=self.launched.append, out=self.out,
                             rank=self.fake_rank([(self.other, "x")]), warm_up=warm_up, **kwargs)
        return code, events

    def test_new_ticket_loads_the_model_while_reading_jira(self):
        code, events = self.run_warm()
        self.assertEqual(code, 0)
        self.assertEqual(events, ["modello", "jira"])
        self.assertIs(self.dense, self.warm)
        self.assertTrue(self.warm.closed)

    def test_no_warm_up_for_known_ticket_or_explicit_folder(self):
        folders.remember("OPS-9", self.repo)
        _, events = self.run_warm()
        self.assertEqual(events, ["jira"])
        shutil.rmtree(self.home / ".claude/cc-panel")
        _, events = self.run_warm(dir_=str(self.other))
        self.assertEqual(events, ["jira"])

    def test_model_loads_while_the_session_history_is_scanned(self):
        original = folders.from_history

        def history(key):
            self.events.append("storia")
            return original(key)
        with mock.patch("cc_panel.folders.from_history", side_effect=history):
            _, events = self.run_warm()
        self.assertEqual(events[:3], ["modello", "storia", "jira"])
        self.assertTrue(self.warm.closed)

    def test_ticket_found_in_history_closes_the_warm_process_without_ranking(self):
        transcript = self.home / ".claude/projects/p/t.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "user", "cwd": str(self.repo), "message": {"content": "OPS-9"}}) + "\n")
        code, events = self.run_warm()
        self.assertEqual(code, 0)
        self.assertEqual(events, ["modello", "jira"])
        self.assertTrue(self.warm.closed)
        self.assertEqual(self.ranked, [])

    def test_ranking_crash_does_not_stop_start(self):
        def broken(issue, warn, dense=None):
            raise RuntimeError("indice rotto")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE):
            code = start.run("OPS-9", auto=True, ask=None, launch=self.launched.append, out=self.out, rank=broken)
        self.assertEqual(code, 0)
        self.assertIn("cd %s &&" % self.repo, self.launched[0])
        self.assertIn("Proposte dal ticket non disponibili: RuntimeError: indice rotto", self.out.getvalue())

    def test_warm_process_is_closed_when_jira_fails(self):
        code, events = self.run_warm(issue=jira.JiraError("Jira non raggiungibile"))
        self.assertEqual(code, 1)
        self.assertEqual(events, ["modello", "jira"])
        self.assertTrue(self.warm.closed)

    def test_terminal_launch_failure_explains_automation_permission(self):
        def denied(_command):
            raise terminal.LaunchError("Ghostty")
        with mock.patch("cc_panel.jira.issue", return_value=ISSUE), mock.patch("sys.stderr", io.StringIO()) as err:
            code = start.run("OPS-9", dir_=str(self.repo), launch=denied, out=self.out)
        self.assertEqual(code, 1)
        self.assertIn("Automazione", err.getvalue())

    def test_start_never_opens_an_editor(self):
        self.assertFalse(hasattr(terminal, "open_editor"))
        self.run_start(("",))
        self.assertEqual(len(self.launched), 1)

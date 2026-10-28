import io
import json
import os
import tempfile
import unittest
from unittest import mock

from cc_panel import cli, feed, repoindex
from tests.helpers import TempHomeCase


class OpenCommandTest(unittest.TestCase):
    def test_open_launches_terminal_in_folder(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("cc_panel.terminal.launch") as launch:
            self.assertEqual(cli.main(["open", tmp]), 0)
        launch.assert_called_once_with("cd %s" % tmp)

    def test_open_rejects_missing_folder(self):
        with mock.patch("cc_panel.terminal.launch") as launch, mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(cli.main(["open", "/non/esiste"]), 1)
        launch.assert_not_called()


class DigestCommandTest(unittest.TestCase):
    def test_digest_reports_count(self):
        with mock.patch("cc_panel.digest.run", return_value=4), mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(cli.main(["digest"]), 0)
        self.assertIn("4", out.getvalue())


class IndexCommandTest(unittest.TestCase):
    def run_cli(self, argv):
        with mock.patch("sys.stdout", io.StringIO()) as out, mock.patch("sys.stderr", io.StringIO()) as err:
            code = cli.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_index_reports_counts_and_missing_semantic_setup(self):
        meta = {"candidates": [1, 2], "chunks": [1, 2, 3]}
        with mock.patch("cc_panel.repoindex.build", return_value=meta), \
                mock.patch("cc_panel.semantic.python", return_value=None):
            code, output = self.run_cli(["index"])
        self.assertEqual(code, 0)
        self.assertIn("2 repo, 3 frammenti", output)
        self.assertIn("cc-panel semantic-setup", output)

    def test_index_already_running(self):
        with mock.patch("cc_panel.repoindex.build", return_value=None):
            code, output = self.run_cli(["index"])
        self.assertEqual(code, 0)
        self.assertIn("già in corso", output)

    def test_index_vectors_failure_is_reported(self):
        with mock.patch("cc_panel.repoindex.build", side_effect=repoindex.VectorsError("IndexMismatch")):
            code, output = self.run_cli(["index"])
        self.assertEqual(code, 1)
        self.assertIn("IndexMismatch", output)

    def test_semantic_setup_passes_the_source_folder(self):
        with mock.patch("cc_panel.semantic.setup", return_value=0) as setup:
            code, _ = self.run_cli(["semantic-setup", "--from", "/scaricati"])
        self.assertEqual(code, 0)
        self.assertEqual(setup.call_args.kwargs["source"], "/scaricati")


class FeedCommandsTest(TempHomeCase):
    def run_cli(self, argv, stdin="", env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), mock.patch("sys.stdout", out), \
                mock.patch("sys.stderr", err), mock.patch.dict("os.environ", env or {}):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_hook_records_event_and_never_fails(self):
        payload = json.dumps({"hook_event_name": "Stop", "session_id": "s1", "cwd": "/r"})
        self.assertEqual(self.run_cli(["hook"], payload)[0], 0)
        self.assertEqual(feed.load()[0]["kind"], "idle")
        for bad in ("", "{rotto", "[1]"):
            self.assertEqual(self.run_cli(["hook"], bad)[0], 0)
        self.assertEqual(len(feed.load()), 1)

    def test_hook_on_exit_plan_mode_reminds_to_record_decisions(self):
        payload = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "ExitPlanMode", "session_id": "s1"})
        code, out, _ = self.run_cli(["hook"], payload)
        context = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(context["hookEventName"], "PostToolUse")
        self.assertIn("cc-panel decide", context["additionalContext"])

    def test_decide_uses_session_from_environment(self):
        code, out, _ = self.run_cli(["decide", "Cache Redis", "--why", "latenza", "--alt", "in-memory",
                                     "--alt", "nessuna", "--watch", "invalidazione", "--learn", "cache-aside"],
                                    env={"CLAUDE_CODE_SESSION_ID": "s9"})
        self.assertEqual(code, 0)
        decision = feed.load()[0]
        self.assertEqual((decision["session"], decision["alternatives"]), ("s9", ["in-memory", "nessuna"]))
        self.assertIn(decision["id"], out)

    def test_decide_outside_a_session_fails_clearly(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            code, _, err = self.run_cli(["decide", "X"])
        self.assertEqual(code, 1)
        self.assertIn("--session", err)
        self.assertEqual(feed.load(), [])

    def test_feed_json_and_text(self):
        feed.decide("s1", "/r/proj", "Cache Redis", learn="cache-aside")
        code, out, _ = self.run_cli(["feed", "--json"])
        self.assertEqual(json.loads(out)["decisions"][0]["title"], "Cache Redis")
        self.assertIn("Cache Redis", self.run_cli(["feed"])[1])

    def test_bar_prints_xbar_menu_with_dive_action(self):
        feed.decide("s1", "/r/proj", "Cache Redis", learn="cache-aside")
        code, out, _ = self.run_cli(["bar"])
        self.assertEqual(code, 0)
        self.assertIn("Cache Redis", out)
        self.assertIn("bin/cc-panel param1=dive", out)

    def test_dive_launches_fork_in_session_folder(self):
        decision = feed.decide("s1", "/r/proj", "Cache Redis", learn="cache-aside")
        with mock.patch("cc_panel.terminal.launch") as launch:
            self.assertEqual(self.run_cli(["dive", decision["id"]])[0], 0)
        command = launch.call_args[0][0]
        self.assertTrue(command.startswith("cd /r/proj && claude --resume s1 --fork-session "))
        self.assertIn("cache-aside", command)

    def test_dive_unknown_id_fails(self):
        with mock.patch("cc_panel.terminal.launch") as launch:
            code, _, err = self.run_cli(["dive", "ffffff"])
        self.assertEqual(code, 1)
        self.assertIn("ffffff", err)
        launch.assert_not_called()

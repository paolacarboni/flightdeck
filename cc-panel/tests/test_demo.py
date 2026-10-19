import io
import json
import unittest
from unittest import mock

from cc_panel import board, cli, demo


class DemoTest(unittest.TestCase):
    def test_model_has_the_board_shape(self):
        model = demo.model(now=2_000_000_000)
        self.assertEqual(set(model["summary"]), {"inProgress", "waitingSessions", "staleSessions"})
        self.assertGreaterEqual(len(model["epics"]), 4)
        for epic in model["epics"]:
            self.assertTrue({"key", "summary", "status", "progress", "items", "repos"} <= set(epic))
            for item in epic["items"]:
                self.assertTrue({"key", "summary", "statusCategory", "session", "nextStep"} <= set(item))
        self.assertTrue(model["proposals"])
        self.assertTrue(any(i["session"].get("status") == "waiting" for e in model["epics"] for i in e["items"]))
        self.assertIn("example", model["baseUrl"])
        board.render_text(model)

    def test_demo_contains_no_real_data(self):
        text = json.dumps(demo.model(now=2_000_000_000)).lower()
        for word in ("/users/", "@"):
            self.assertNotIn(word, text)

    def test_board_demo_does_not_call_jira(self):
        with mock.patch("cc_panel.jira.search") as search, mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(cli.main(["board", "--demo", "--json"]), 0)
        search.assert_not_called()
        self.assertTrue(json.loads(out.getvalue())["epics"])

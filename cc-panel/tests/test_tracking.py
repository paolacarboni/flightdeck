import json
from unittest import mock

from cc_panel import jira, tracking
from tests.helpers import TempHomeCase

SID = "8643e4dd-5c49-46ea-a509-638556b632be"


class TrackingTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % SID)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"type": "user", "cwd": "/Users/x/repo", "message": {"content": "Estrai il lineage"}}) + "\n")

    def test_link_and_ignore_are_persisted(self):
        tracking.link(SID, "OPS-5")
        tracking.ignore("altra")
        self.assertEqual(tracking.links(), {SID: "OPS-5"})
        self.assertEqual(tracking.ignored(), {"altra"})

    def test_track_creates_task_under_epic_and_links(self):
        with mock.patch("cc_panel.jira.create_issue", return_value="APP-500") as create:
            key = tracking.track(SID, epic="APP-321")
        self.assertEqual(key, "APP-500")
        args, kwargs = create.call_args
        self.assertEqual(args[:3], ("APP", jira.TASK_TYPE, "Estrai il lineage"))
        self.assertEqual(kwargs["parent"], "APP-321")
        self.assertIn(SID, args[3])
        self.assertIn("/Users/x/repo", args[3])
        self.assertEqual(tracking.links(), {SID: "APP-500"})

    def test_track_new_epic_in_default_project(self):
        import os
        os.environ["CC_PANEL_DEFAULT_PROJECT"] = "OPS"
        with mock.patch("cc_panel.jira.create_issue", return_value="OPS-900") as create:
            tracking.track(SID, new_epic=True, summary="Data lineage")
        args, kwargs = create.call_args
        self.assertEqual(args[:3], ("OPS", jira.EPIC_TYPE, "Data lineage"))
        self.assertIsNone(kwargs.get("parent"))

    def test_jira_failure_does_not_link(self):
        with mock.patch("cc_panel.jira.create_issue", side_effect=jira.JiraError("Jira ha risposto 400")):
            with self.assertRaises(jira.JiraError):
                tracking.track(SID, epic="OPS-1")
        self.assertEqual(tracking.links(), {})

    def test_unknown_session_raises(self):
        with self.assertRaises(tracking.TrackingError):
            tracking.track("sconosciuta", epic="OPS-1")

    def test_resume_launches_in_session_folder(self):
        launched = []
        tracking.resume(SID, launch=launched.append)
        self.assertEqual(launched, ["cd /Users/x/repo && claude --ide --resume %s" % SID])

    def test_track_several_sessions_links_all(self):
        other = "1111aaaa-0000-0000-0000-000000000000"
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % other)
        path.write_text(json.dumps({"type": "user", "cwd": "/Users/x/repo", "message": {"content": "altro"}}) + "\n")
        with mock.patch("cc_panel.jira.create_issue", return_value="OPS-901") as create:
            tracking.track([SID, other], epic="OPS-1", summary="Tema")
        self.assertIn(other, create.call_args[0][3])
        self.assertEqual(tracking.links(), {SID: "OPS-901", other: "OPS-901"})

    def test_new_epic_without_default_project_is_refused(self):
        with mock.patch("cc_panel.jira.create_issue") as create:
            with self.assertRaises(tracking.TrackingError):
                tracking.track(SID, new_epic=True)
        create.assert_not_called()

import json
import os
from pathlib import Path

from cc_panel import config
from tests.helpers import TempHomeCase


class ConfigTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        for name in config.ENV.values():
            os.environ.pop(name, None)

    def write(self, data):
        path = self.home / ".config/cc-panel/config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_values_from_file(self):
        self.write({"jira_base_url": "https://example.atlassian.net/", "jira_email": "me@example.com",
                    "default_project": "OPS", "notes_dir": "~/notes", "projects_dir": "~/code"})
        self.assertEqual(config.jira_base_url(), "https://example.atlassian.net")
        self.assertEqual(config.jira_email(), "me@example.com")
        self.assertEqual(config.default_project(), "OPS")
        self.assertEqual(config.notes_dir(), self.home / "notes")
        self.assertEqual(config.projects_dir(), self.home / "code")

    def test_environment_overrides_file(self):
        self.write({"jira_base_url": "https://a.atlassian.net", "jira_email": "a@a"})
        os.environ["CC_PANEL_JIRA_URL"] = "https://b.atlassian.net"
        os.environ["CC_PANEL_JIRA_EMAIL"] = "b@b"
        self.addCleanup(os.environ.pop, "CC_PANEL_JIRA_URL", None)
        self.addCleanup(os.environ.pop, "CC_PANEL_JIRA_EMAIL", None)
        self.assertEqual((config.jira_base_url(), config.jira_email()), ("https://b.atlassian.net", "b@b"))

    def test_defaults(self):
        self.assertEqual(config.notes_dir(), self.home / ".cc-panel/notes")
        self.assertEqual(config.projects_dir(), self.home / "Projects")
        self.assertIsNone(config.default_project())

    def test_missing_jira_url_is_a_readable_error(self):
        with self.assertRaises(config.ConfigError) as ctx:
            config.jira_base_url()
        self.assertIn("config.json", str(ctx.exception))

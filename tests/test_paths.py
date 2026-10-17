from cc_panel import paths
from tests.helpers import TempHomeCase


class PathsTest(TempHomeCase):
    def test_home_and_state_follow_env(self):
        self.assertEqual(paths.home(), self.home)
        self.assertEqual(paths.state_file(), self.home / ".claude/cc-panel/state.json")

    def test_ticket_note_lives_in_notes_dir(self):
        self.assertEqual(paths.ticket_note("AI-1"), self.vault / "Jira/AI-1.md")

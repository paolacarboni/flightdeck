import json

from cc_panel import folders
from tests.helpers import TempHomeCase


class FoldersTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.repo_a = self.home / "Projects/a"
        self.repo_b = self.home / "Projects/group/b"
        for repo in (self.repo_a, self.repo_b):
            (repo / ".git").mkdir(parents=True)

    def transcript(self, name, lines):
        path = self.home / ".claude/projects/x" / ("%s.jsonl" % name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")

    def msg(self, cwd, text, kind="user"):
        return {"type": kind, "cwd": str(cwd), "message": {"content": text}}

    def test_history_counts_rank_folders(self):
        self.transcript("s1", [self.msg(self.repo_b, "lavoro su AI-34")])
        self.transcript("s2", [self.msg(self.repo_b, "ancora AI-34", "assistant")])
        self.transcript("s3", [self.msg(self.repo_a, "AI-34 qui"), self.msg(self.repo_a, "AI-34 di nuovo"),
                               self.msg(self.repo_a, "e ancora AI-34")])
        # Un voto per sessione: repo_b ha 2 sessioni, repo_a una sola con tre messaggi.
        self.assertEqual(folders.suggest("AI-34", None)[:2], [self.repo_b, self.repo_a])

    def test_key_boundaries_and_non_message_lines(self):
        self.transcript("s1", [
            self.msg(self.repo_a, "solo AI-340 e XAI-34"),
            {"type": "attachment", "cwd": str(self.repo_b), "content": "hook cita AI-34"},
        ])
        self.assertEqual(folders.from_history("AI-34"), [])

    def test_session_votes_for_its_starting_folder(self):
        self.transcript("s1", [self.msg(self.repo_a, "inizio senza ticket"), self.msg(self.repo_b, "ora AI-34")])
        self.assertEqual(folders.from_history("AI-34"), [self.repo_a])

    def test_session_started_in_home_does_not_vote(self):
        self.transcript("s1", [self.msg(self.home, "inizio"), self.msg(self.repo_b, "ora AI-34")])
        self.assertEqual(folders.from_history("AI-34"), [])

    def test_tool_results_are_ignored(self):
        tool_result = {"type": "user", "cwd": str(self.repo_a),
                       "message": {"content": [{"type": "tool_result", "content": "AI-34 Backlog"}]}}
        self.transcript("s1", [tool_result])
        self.assertEqual(folders.from_history("AI-34"), [])

    def test_text_blocks_in_list_content_count(self):
        line = {"type": "assistant", "cwd": str(self.repo_a),
                "message": {"content": [{"type": "text", "text": "chiudo AI-34"}]}}
        self.transcript("s1", [line])
        self.assertEqual(folders.from_history("AI-34"), [self.repo_a])

    def test_moved_folder_is_relocated_under_projects(self):
        self.transcript("s1", [self.msg(self.home / "Projects/b", "AI-34")])
        self.assertEqual(folders.from_history("AI-34"), [self.repo_b])

    def test_missing_folders_and_home_are_skipped(self):
        self.transcript("s1", [self.msg(self.home / "gone", "AI-34"), self.msg(self.home, "AI-34")])
        self.assertEqual(folders.from_history("AI-34"), [])

    def test_order_remembered_then_key_then_epic_then_repos(self):
        self.transcript("s1", [self.msg(self.repo_b, "epica AI-1")])
        folders.remember("AI-34", self.repo_a)
        self.assertEqual(folders.suggest("AI-34", "AI-1"), [self.repo_a, self.repo_b])
        self.assertEqual(folders.remembered("AI-34"), self.repo_a)

    def test_repos_found_under_projects(self):
        self.assertEqual(folders.repos(), [self.repo_a, self.repo_b])

    def test_remembered_folder_that_no_longer_exists_is_ignored(self):
        folders.remember("AI-34", self.home / "gone")
        self.assertIsNone(folders.remembered("AI-34"))

    def test_corrupted_state_is_treated_as_empty(self):
        state = self.home / ".claude/cc-panel/state.json"
        state.parent.mkdir(parents=True)
        state.write_text("{non json")
        self.assertIsNone(folders.remembered("AI-34"))
        folders.remember("AI-34", self.repo_a)
        self.assertEqual(folders.remembered("AI-34"), self.repo_a)

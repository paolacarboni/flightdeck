import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from cc_panel import gitstate


def git(repo, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = "@%d +0000" % when
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, capture_output=True, env=env)


class GitStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.repo = self.base / "repo"
        (self.repo / "sub").mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        self._tmp.cleanup()

    def commit(self, name, days_ago=0):
        (self.repo / name).write_text(name)
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", name, when=int(time.time()) - days_ago * 86400)

    def test_root_of_subfolder_is_repo(self):
        self.assertEqual(gitstate.root(self.repo / "sub"), self.repo)
        self.assertIsNone(gitstate.root(self.base))

    def test_status_counts_and_age(self):
        self.commit("a.txt", days_ago=3)
        (self.repo / "a.txt").write_text("cambiato")
        (self.repo / "nuovo.txt").write_text("x")
        status = gitstate.status(self.repo)
        self.assertEqual(status, {"branch": "main", "dirty": 2, "ahead": 0, "lastCommitDays": 3})

    def test_ahead_of_upstream(self):
        self.commit("a.txt")
        remote = self.base / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        git(self.repo, "remote", "add", "origin", str(remote))
        git(self.repo, "push", "-q", "-u", "origin", "main")
        self.commit("b.txt")
        self.commit("c.txt")
        self.assertEqual(gitstate.status(self.repo)["ahead"], 2)

    def test_repo_without_commits(self):
        status = gitstate.status(self.repo)
        self.assertEqual((status["branch"], status["lastCommitDays"]), ("main", None))

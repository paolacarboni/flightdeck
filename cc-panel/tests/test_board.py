import json
import subprocess
from unittest import mock

from cc_panel import board, jira
from tests.helpers import TempHomeCase


def issue(key, summary, type_, category="indeterminate", parent=None, status="IN LAVORAZIONE"):
    fields = {"summary": summary, "issuetype": {"name": type_},
              "status": {"name": status, "statusCategory": {"key": category}}}
    if parent:
        fields["parent"] = parent
    return {"key": key, "fields": fields}


def ref(key, type_):
    return {"key": key, "fields": {"issuetype": {"name": type_}}}


def fake_search(jql, fields):
    if jql.startswith("assignee"):
        return [issue("OPS-10", "Task diretto", "Task", parent=ref("OPS-1", "Epic")),
                issue("OPS-11", "Sottotask", "Sottotask", "new", parent=ref("OPS-12", "Story"), status="Backlog"),
                issue("OPS-20", "Senza epica", "Task", "new", status="Backlog")]
    if jql == "key in (OPS-12)":
        return [{"key": "OPS-12", "fields": {"parent": ref("OPS-1", "Epic")}}]
    if jql == "key in (OPS-1)":
        return [issue("OPS-1", "Epica Uno", "Epic")]
    if jql == "parent in (OPS-1)":
        return [dict(issue("OPS-10", "", "Task"), fields=dict(issue("OPS-10", "", "Task")["fields"], parent=ref("OPS-1", "Epic"))),
                dict(issue("OPS-12", "", "Story", "new"), fields=dict(issue("OPS-12", "", "Story", "new")["fields"], parent=ref("OPS-1", "Epic"))),
                dict(issue("OPS-13", "", "Task", "done"), fields=dict(issue("OPS-13", "", "Task", "done")["fields"], parent=ref("OPS-1", "Epic")))]
    raise AssertionError("JQL inattesa: %s" % jql)


class BoardTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.repo = self.home / "Projects/repo"
        (self.repo / "sub").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)

    def transcript(self, name, cwd, text, title=None):
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % name)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [{"type": "user", "cwd": str(cwd), "message": {"content": text}}]
        if title:
            lines.append({"type": "custom-title", "customTitle": title})
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")

    def build(self):
        with mock.patch("cc_panel.jira.search", side_effect=fake_search):
            return board.build()

    def test_missing_or_stale_repo_index_is_rebuilt_in_background(self):
        self.build()
        self.spawned_index.assert_called_once()
        self.spawned_index.reset_mock()
        with mock.patch("cc_panel.repoindex.load", return_value={"builtAt": __import__("time").time()}):
            self.build()
        self.spawned_index.assert_not_called()

    def test_items_grouped_by_epic_with_progress(self):
        model = self.build()
        [epic] = model["epics"]
        self.assertEqual((epic["key"], epic["summary"]), ("OPS-1", "Epica Uno"))
        self.assertEqual([i["key"] for i in epic["items"]], ["OPS-10", "OPS-11"])
        self.assertEqual(epic["progress"], {"done": 1, "indeterminate": 1, "new": 1})
        self.assertEqual([i["key"] for i in model["noEpic"]], ["OPS-20"])
        self.assertEqual(model["summary"]["inProgress"], 1)

    def test_epic_repos_from_sessions_on_its_tickets_grouped_by_root(self):
        self.transcript("s1", self.repo, "lavoro su OPS-13")
        self.transcript("s2", self.repo / "sub", "e su OPS-1")
        [repo] = self.build()["epics"][0]["repos"]
        self.assertEqual((repo["name"], repo["sessions"], repo["branch"]), ("repo", 2, "main"))
        self.assertEqual(repo["path"], str(self.repo.resolve()))

    def test_session_state_and_next_step_per_item(self):
        sessions_dir = self.home / ".claude/sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "1.json").write_text(json.dumps({"sessionId": "o", "name": "OPS-10 x", "status": "waiting"}))
        self.transcript("c1", self.repo, "ciao", title="OPS-11 y")
        note = self.vault / "Jira/OPS-10.md"
        note.parent.mkdir(parents=True)
        note.write_text("## Ripresa\n\n### 2026-10-17 10:00\n\n**Prossimo passo:** scrivere test\n")
        model = self.build()
        items = {i["key"]: i for i in model["epics"][0]["items"]}
        self.assertEqual(items["OPS-10"]["session"], {"state": "open", "status": "waiting", "sessionId": "o"})
        self.assertEqual(items["OPS-11"]["session"]["state"], "closed")
        self.assertEqual(model["noEpic"][0]["session"]["state"], "none")
        self.assertEqual(items["OPS-10"]["nextStep"], "scrivere test")
        self.assertIsNone(items["OPS-11"]["nextStep"])
        self.assertEqual(model["summary"]["waitingSessions"], 1)

    def test_jira_error_serves_cache_as_stale(self):
        self.build()
        with mock.patch("cc_panel.jira.search", side_effect=jira.JiraError("Jira non raggiungibile")):
            model = board.build()
        self.assertTrue(model["stale"])
        self.assertIn("non raggiungibile", model["error"])
        self.assertEqual(model["epics"][0]["key"], "OPS-1")

    def test_jira_error_without_cache_gives_empty_model(self):
        with mock.patch("cc_panel.jira.search", side_effect=jira.JiraError("token assente")):
            model = board.build()
        self.assertEqual((model["epics"], model["noEpic"], model["error"]), ([], [], "token assente"))

    def test_non_git_project_folder_is_kept_without_git_state(self):
        plain = self.home / "Projects/cartella"
        plain.mkdir()
        self.transcript("s1", plain, "lavoro su OPS-10")
        [repo] = self.build()["epics"][0]["repos"]
        self.assertEqual((repo["name"], repo["branch"], repo["sessions"]), ("cartella", None, 1))

    def test_generic_sessions_weigh_less_than_specific_ones(self):
        generic = self.home / "Projects/generico"
        subprocess.run(["git", "init", "-q", "-b", "main", str(generic)], check=True)
        # repo: una sessione solo sull'epica (peso 1). generico: due sessioni che citano
        # anche chiavi di altro (peso 1/3 ciascuna, totale 2/3).
        self.transcript("s1", self.repo, "OPS-10")
        self.transcript("g1", generic, "OPS-10 OPS-20 OPS-99")
        self.transcript("g2", generic, "OPS-11 OPS-20 OPS-98")
        repos = self.build()["epics"][0]["repos"]
        self.assertEqual([(r["name"], r["sessions"]) for r in repos], [("repo", 1), ("generico", 2)])


class UntrackedTest(BoardTest):
    DAY = 86400

    def closed(self, sid, prompts, days_ago=1, title=None, text="", cwd=None):
        import os
        import time
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [{"type": "user", "cwd": str(cwd or self.repo), "message": {"content": "%s domanda %d" % (text, i)}}
                 for i in range(prompts)]
        if title:
            lines.append({"type": "custom-title", "customTitle": title})
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        when = time.time() - days_ago * self.DAY
        os.utime(path, (when, when))

    def opened(self, sid, name, status="idle", hours_ago=1):
        import time
        folder = self.home / ".claude/sessions"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ("%s.json" % sid)).write_text(json.dumps({
            "sessionId": sid, "name": name, "status": status, "cwd": str(self.repo),
            "statusUpdatedAt": int((time.time() - hours_ago * 3600) * 1000)}))

    def untracked_ids(self):
        return [u["sessionId"] for u in self.build()["untracked"]]

    def test_linked_session_shows_on_item(self):
        from cc_panel import tracking
        self.opened("free", "lineage", status="waiting")
        tracking.link("free", "OPS-11")
        items = {i["key"]: i for i in self.build()["epics"][0]["items"]}
        self.assertEqual(items["OPS-11"]["session"]["sessionId"], "free")
        self.assertEqual(items["OPS-11"]["session"]["status"], "waiting")

    def test_stale_open_sessions(self):
        self.opened("stale", "OPS-10 lavoro", hours_ago=50)
        self.opened("fresh", "nuova", hours_ago=2)
        model = self.build()
        items = {i["key"]: i for i in model["epics"][0]["items"]}
        self.assertEqual(items["OPS-10"]["session"]["staleDays"], 2)
        self.assertEqual(model["summary"]["staleSessions"], 1)


class ProposalsTest(UntrackedTest):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("cc_panel.board._spawn_digest")
        self.spawn = patcher.start()
        self.addCleanup(patcher.stop)

    def work(self, sid, days_ago=1):
        import os
        import time
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [{"type": "user", "cwd": str(self.repo), "message": {"content": "passo %d" % i}} for i in range(4)]
        lines += [{"type": "assistant", "cwd": str(self.repo), "message": {"content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/f%d" % i}}]}} for i in range(3)]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        when = time.time() - days_ago * self.DAY
        os.utime(path, (when, when))
        return when

    def evaluated(self, results):
        from cc_panel import history
        mtimes = {s["sessionId"]: s["mtime"] for s in history.index()}
        cache = {sid: {"mtime": mtimes[sid], "evaluatedAt": 0, "result": result} for sid, result in results.items()}
        target = self.home / ".claude/cc-panel/digest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(cache))

    def proposal(self, title, valuable=True, existing=None, epic=None):
        return {"valuable": valuable, "title": title, "why": "perché", "existingKey": existing, "epicKey": epic}

    def grouped(self, groups):
        import time
        from cc_panel import digest, history
        target = self.home / ".claude/cc-panel/groups.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        candidates = digest.candidates(history.index(), {}, set(), time.time())
        target.write_text(json.dumps({"inputHash": digest.input_hash(candidates, digest.load()), "groups": groups}))

    def test_proposals_are_the_groups(self):
        self.work("a", days_ago=1)
        self.work("b", days_ago=2)
        self.evaluated({"a": self.proposal("A"), "b": self.proposal("B")})
        self.grouped([{"title": "Tema", "why": "perché", "epicKey": "OPS-1", "sessionIds": ["b", "a"]}])
        model = self.build()
        self.assertNotIn("untracked", model)
        [proposal] = model["proposals"]
        self.assertEqual((proposal["title"], proposal["epicKey"], proposal["epicSummary"]), ("Tema", "OPS-1", "Epica Uno"))
        self.assertEqual(proposal["sessionIds"], ["a", "b"])
        self.assertEqual(proposal["sessionId"], "a")
        self.assertEqual(proposal["folder"], "repo")

    def test_group_sessions_no_longer_candidates_are_dropped(self):
        from cc_panel import tracking
        self.work("a")
        self.work("b")
        self.evaluated({"a": self.proposal("A"), "b": self.proposal("B")})
        self.grouped([{"title": "Tema", "why": "w", "epicKey": "ZZ-1", "sessionIds": ["a", "b"]},
                      {"title": "Solo b", "why": "w", "epicKey": None, "sessionIds": ["b"]}])
        tracking.ignore("b")
        proposals = self.build()["proposals"]
        self.assertEqual([(p["title"], p["sessionIds"], p["epicKey"]) for p in proposals], [("Tema", ["a"], None)])

    def test_background_evaluation_started_only_when_pending(self):
        self.build()
        self.spawn.assert_not_called()
        self.work("a")
        self.build()
        self.spawn.assert_called_once()

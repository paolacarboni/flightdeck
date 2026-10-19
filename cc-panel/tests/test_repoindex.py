import json
import subprocess
import time
from unittest import mock

from cc_panel import repoindex
from tests.helpers import TempHomeCase

README = """[![build](https://ci/badge.svg)](https://ci)

# App — servizio di fatturazione

Calcola le fatture dei clienti.

```bash
make segreto-nel-codice
```

<img src="x.png">
""" + "Riga di dettaglio sul dominio.\n" * 120


def session(sid, cwd, keys=(), files=(), title=None, prompts=("primo messaggio",), mtime=1.0):
    return {"sessionId": sid, "cwd": str(cwd), "keys": set(keys), "title": title, "mtime": mtime,
            "prompts": len(prompts), "firstPrompt": prompts[0] if prompts else None, "edits": len(files),
            "commits": 0, "files": [str(f) for f in files], "promptSample": list(prompts)}


class RepoIndexTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.projects = self.home / "Projects"
        self.app = self.projects / "Acme/team/app"
        (self.app / ".git/worktrees/app-OPS-9").mkdir(parents=True)
        (self.app / ".git/config").write_text('[remote "origin"]\n\turl = git@github.com:acme/app.git\n')
        (self.app / "README.md").write_text(README)
        (self.app / "package.json").write_text(json.dumps({"description": "Fatturazione clienti"}))
        for folder in ("src/main", "infra/telemetry", "node_modules/pkg", ".github/workflows"):
            (self.app / folder).mkdir(parents=True)
        self.worktree = self.projects / "Acme/team/app-OPS-9"
        self.worktree.mkdir(parents=True)
        (self.worktree / ".git").write_text("gitdir: %s\n" % (self.app / ".git/worktrees/app-OPS-9"))
        self.notes = self.projects / "Personal/notes"
        (self.notes / ".git").mkdir(parents=True)

    def group_of(self, candidates, folder):
        return next(c for c in candidates if str(folder) in c["folders"])

    def test_clone_and_worktree_share_one_group_represented_by_clone(self):
        found = repoindex.candidates()
        self.assertEqual(len(found), 2)
        app = self.group_of(found, self.app)
        self.assertEqual(app["folder"], str(self.app))
        self.assertEqual(sorted(app["folders"]), sorted([str(self.app), str(self.worktree)]))
        self.assertEqual(app["group"], "origin:app")
        self.assertIn("app", app["names"])
        self.assertIn("app-OPS-9", app["names"])

    def test_worktrees_in_hidden_worktrees_folder_join_the_group(self):
        hidden = self.app / ".worktrees/feat-OPS-7"
        hidden.mkdir(parents=True)
        (hidden / ".git").write_text("gitdir: %s\n" % (self.app / ".git/worktrees/feat-OPS-7"))
        (self.app / ".git/worktrees/feat-OPS-7").mkdir()
        app = self.group_of(repoindex.candidates(), self.app)
        self.assertIn(str(hidden), app["folders"])
        self.assertEqual(app["folder"], str(self.app))

    def test_worktree_of_missing_repo_is_its_own_group(self):
        orphan = self.projects / "old/orphan"
        orphan.mkdir(parents=True)
        (orphan / ".git").write_text("gitdir: /sparito/.git/worktrees/orphan\n")
        group = self.group_of(repoindex.candidates(), orphan)
        self.assertEqual(group["folders"], [str(orphan)])
        self.assertEqual(group["group"], str(orphan))

    def test_scan_skips_hidden_dependency_and_too_deep_folders(self):
        for folder in (".cache/x", "a/node_modules/y", "a/b/c/d/e/f"):
            (self.projects / folder / ".git").mkdir(parents=True)
        self.assertEqual(len(repoindex.candidates()), 2)

    def test_chunks_describe_name_structure_and_readme(self):
        found = repoindex.candidates()
        chunks = repoindex.chunks(found, [])
        index = found.index(self.group_of(found, self.app))
        mine = [c for c in chunks if c["group"] == index]
        name = next(c for c in mine if c["kind"] == "nome")
        for text in ("app", "Acme team app", "Fatturazione clienti"):
            self.assertIn(text, name["text"])
        structure = next(c for c in mine if c["kind"] == "struttura")["text"]
        self.assertIn("infra/telemetry", structure)
        self.assertNotIn("node_modules", structure)
        self.assertNotIn(".github", structure)
        readme = [c for c in mine if c["kind"] == "readme"]
        self.assertEqual(len(readme), repoindex.README_BLOCKS)
        self.assertTrue(all(len(c["text"]) <= repoindex.README_BLOCK for c in readme))
        self.assertIn("servizio di fatturazione", readme[0]["text"])
        self.assertNotIn("badge.svg", readme[0]["text"])
        self.assertNotIn("segreto-nel-codice", " ".join(c["text"] for c in readme))
        self.assertEqual(readme[0]["label"], "README: App — servizio di fatturazione")

    def test_repo_without_readme_or_remote_has_name_and_structure_only(self):
        found = repoindex.candidates()
        index = found.index(self.group_of(found, self.notes))
        kinds = [c["kind"] for c in repoindex.chunks(found, []) if c["group"] == index]
        self.assertEqual(kinds, ["nome", "struttura"])

    def test_sessions_go_to_edited_repo_else_start_folder(self):
        found = repoindex.candidates()
        app = found.index(self.group_of(found, self.app))
        notes = found.index(self.group_of(found, self.notes))
        sessions = [
            session("s1", self.notes, ["OPS-1"], [self.worktree / "src/a.py", self.app / "b.py"], title="OPS-1 Fatture"),
            session("s2", self.notes, prompts=("appunti della riunione", "secondo")),
            session("s3", self.notes, ["OPS-1", "OPS-2", "OPS-3", "OPS-4"], [self.app / "c.py"]),
            session("s4", self.home, prompts=("dalla home",)),
        ]
        by_group = {}
        for chunk in repoindex.chunks(found, sessions):
            if chunk["kind"] == "sessione":
                by_group.setdefault(chunk["group"], []).append(chunk["text"])
        self.assertEqual(by_group, {app: ["OPS-1 Fatture primo messaggio"], notes: ["appunti della riunione secondo"]})

    def test_moved_folders_are_found_by_name(self):
        other_app = self.projects / "Altro/app"
        (other_app / ".git").mkdir(parents=True)
        (other_app / ".git/config").write_text('[remote "origin"]\n\turl = https://github.com/x/app-copia.git\n')
        found = repoindex.candidates()
        app = found.index(self.group_of(found, self.app))
        notes = found.index(self.group_of(found, self.notes))
        sessions = [
            # cartella spostata fuori da ~/Projects: «notes» è un nome unico
            session("s1", self.home / "notes", prompts=("prima della riorganizzazione",)),
            # file in un percorso vecchio: due candidati «app», vince quello con il genitore «team» uguale
            session("s2", self.home / "gone", files=[self.home / "Projects/team/app/src/a.py"], title="OPS-5 Lavoro"),
            # due «app» e nessun genitore che distingue: ambiguo, la sessione resta fuori
            session("s3", self.home / "vecchio/app", prompts=("ambiguo",)),
        ]
        texts = {(c["group"], c["text"]) for c in repoindex.chunks(found, sessions) if c["kind"] == "sessione"}
        self.assertEqual(texts, {(notes, "prima della riorganizzazione"), (app, "OPS-5 Lavoro primo messaggio")})

    def test_session_chunks_keep_the_most_recent(self):
        found = repoindex.candidates()
        sessions = [session("s%d" % i, self.notes, prompts=("lavoro %d" % i,), mtime=i)
                    for i in range(repoindex.SESSION_LIMIT + 5)]
        texts = [c["text"] for c in repoindex.chunks(found, sessions) if c["kind"] == "sessione"]
        self.assertEqual(len(texts), repoindex.SESSION_LIMIT)
        self.assertIn("lavoro %d" % (repoindex.SESSION_LIMIT + 4), texts)
        self.assertNotIn("lavoro 0", texts)

    def test_build_writes_meta_then_vectors(self):
        calls = []
        meta = repoindex.build(now=1000.0, indexed=[], vectors=lambda folder: calls.append(folder))
        self.assertEqual(calls, [repoindex.index_dir()])
        saved = repoindex.load()
        self.assertEqual(saved, meta)
        self.assertEqual(saved["version"], repoindex.VERSION)
        self.assertEqual(saved["builtAt"], 1000.0)
        self.assertEqual(len(saved["candidates"]), 2)
        self.assertTrue(saved["chunks"])

    def test_build_respects_a_fresh_lock(self):
        lock = repoindex.index_dir() / "index.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(str(time.time()))
        self.assertIsNone(repoindex.build(indexed=[], vectors=lambda folder: None))
        self.assertIsNone(repoindex.load())
        lock.write_text(str(time.time() - repoindex.LOCK_STALE_SECONDS - 1))
        self.assertIsNotNone(repoindex.build(indexed=[], vectors=lambda folder: None))
        self.assertFalse(lock.exists())

    def test_vectors_failure_in_the_venv_is_raised(self):
        failed = subprocess.CompletedProcess([], 1, "", "Traceback\nIndexMismatch: vettori")
        with mock.patch("cc_panel.semantic.python", return_value="/venv/bin/python"), \
                mock.patch("subprocess.run", return_value=failed):
            with self.assertRaises(repoindex.VectorsError) as raised:
                repoindex.build(indexed=[])
        self.assertIn("IndexMismatch: vettori", str(raised.exception))
        self.assertIsNotNone(repoindex.load())
        self.assertFalse((repoindex.index_dir() / "index.lock").exists())

    def test_without_semantic_setup_the_index_stays_lexical(self):
        with mock.patch("cc_panel.semantic.python", return_value=None), mock.patch("subprocess.run") as run:
            self.assertIsNotNone(repoindex.build(indexed=[]))
        run.assert_not_called()

    def test_load_rejects_other_versions_and_corruption(self):
        repoindex.index_dir().mkdir(parents=True)
        meta = repoindex.index_dir() / "meta.json"
        meta.write_text(json.dumps({"version": repoindex.VERSION + 1, "candidates": [], "chunks": []}))
        self.assertIsNone(repoindex.load())
        meta.write_text("{rotto")
        self.assertIsNone(repoindex.load())

    def test_staleness(self):
        self.assertTrue(repoindex.is_stale(None, 0))
        meta = {"builtAt": 1000.0}
        self.assertFalse(repoindex.is_stale(meta, 1000.0 + repoindex.MAX_AGE_SECONDS - 1))
        self.assertTrue(repoindex.is_stale(meta, 1000.0 + repoindex.MAX_AGE_SECONDS + 1))

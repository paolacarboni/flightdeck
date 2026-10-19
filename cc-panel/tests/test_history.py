import json
import os

from cc_panel import history
from tests.helpers import TempHomeCase


class HistoryIndexTest(TempHomeCase):
    def write(self, name, lines, mtime=1000):
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        os.utime(path, (mtime, mtime))
        return path

    def test_session_fields(self):
        self.write("s1", [
            {"type": "user", "cwd": "/start", "message": {"content": "parto"}},
            {"type": "user", "cwd": "/altrove", "message": {"content": "lavoro su OPS-34 e APP-410"}},
            {"type": "assistant", "cwd": "/altrove", "message": {"content": [{"type": "text", "text": "chiudo OPS-7"}]}},
            {"type": "attachment", "content": "hook: OPS-999"},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "OPS-888"}]}},
            {"type": "custom-title", "customTitle": "OPS-34 titolo"},
        ], mtime=1234)
        [session] = history.index()
        self.assertEqual(session["sessionId"], "s1")
        self.assertEqual(session["cwd"], "/start")
        self.assertEqual(session["keys"], {"OPS-34", "APP-410", "OPS-7"})
        self.assertEqual(session["title"], "OPS-34 titolo")
        self.assertEqual(session["mtime"], 1234)

    def test_unchanged_file_served_from_cache(self):
        self.write("s1", [{"type": "user", "cwd": "/a", "message": {"content": "OPS-1"}}])
        history.index()
        cache_file = self.home / ".claude/cc-panel/history.json"
        cache = json.loads(cache_file.read_text())
        [entry] = cache["files"].values()
        entry["cwd"] = "/dalla-cache"
        cache_file.write_text(json.dumps(cache))
        self.assertEqual(history.index()[0]["cwd"], "/dalla-cache")

    def test_changed_file_is_reread(self):
        self.write("s1", [{"type": "user", "cwd": "/a", "message": {"content": "OPS-1"}}], mtime=1000)
        history.index()
        self.write("s1", [{"type": "user", "cwd": "/b", "message": {"content": "OPS-2"}}], mtime=2000)
        [session] = history.index()
        self.assertEqual((session["cwd"], session["keys"]), ("/b", {"OPS-2"}))

    def test_corrupted_cache_is_rebuilt(self):
        cache_file = self.home / ".claude/cc-panel/history.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text("{rotta")
        self.write("s1", [{"type": "user", "cwd": "/a", "message": {"content": "OPS-1"}}])
        self.assertEqual(history.index()[0]["keys"], {"OPS-1"})

    def test_deleted_transcript_disappears(self):
        path = self.write("s1", [{"type": "user", "cwd": "/a", "message": {"content": "OPS-1"}}])
        history.index()
        path.unlink()
        self.assertEqual(history.index(), [])

    def test_prompts_and_first_prompt(self):
        self.write("s1", [
            {"type": "user", "cwd": "/a", "message": {"content": "<command-name>/clear</command-name>"}},
            {"type": "user", "cwd": "/a", "isMeta": True, "message": {"content": "meta"}},
            {"type": "user", "cwd": "/a", "message": {"content": "Estrai le tabelle\n  di lineage " + "x" * 100}},
            {"type": "user", "cwd": "/a", "message": {"content": [{"type": "tool_result", "content": "out"}]}},
            {"type": "assistant", "cwd": "/a", "message": {"content": "ok"}},
            {"type": "user", "cwd": "/a", "message": {"content": "continua"}},
        ])
        [session] = history.index()
        self.assertEqual(session["prompts"], 2)
        self.assertTrue(session["firstPrompt"].startswith("Estrai le tabelle di lineage x"))
        self.assertEqual(len(session["firstPrompt"]), 80)

    def test_cache_from_previous_version_is_rebuilt(self):
        self.write("s1", [{"type": "user", "cwd": "/a", "message": {"content": "OPS-1"}}])
        cache_file = self.home / ".claude/cc-panel/history.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({"version": 1, "files": {}}))
        self.assertEqual(history.index()[0]["prompts"], 1)

    def test_work_evidence_and_prompt_sample(self):
        def tool(name, **inputs):
            return {"type": "assistant", "cwd": "/a", "message": {"content": [
                {"type": "tool_use", "name": name, "input": inputs}]}}
        lines = [{"type": "user", "cwd": "/a", "message": {"content": "messaggio %d %s" % (i, "y" * 300)}}
                 for i in range(8)]
        lines += [tool("Edit", file_path="/a/x.py"), tool("Write", file_path="/a/y.py"),
                  tool("Edit", file_path="/a/x.py"), tool("Read", file_path="/a/z.py"),
                  tool("Bash", command="git -C /a commit -q -m 'feat: x'"), tool("Bash", command="ls")]
        self.write("s1", lines)
        [session] = history.index()
        self.assertEqual((session["edits"], session["commits"]), (3, 1))
        self.assertEqual(session["files"], ["/a/x.py", "/a/y.py"])
        sample = session["promptSample"]
        self.assertEqual(len(sample), 6)
        self.assertTrue(sample[0].startswith("messaggio 0"))
        self.assertTrue(sample[-1].startswith("messaggio 7"))
        self.assertEqual(len(sample[0]), 200)

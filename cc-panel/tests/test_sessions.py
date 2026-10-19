import json

from cc_panel import sessions
from tests.helpers import TempHomeCase


class FindOpenTest(TempHomeCase):
    def write(self, name, data):
        path = self.home / ".claude/sessions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data))

    def test_finds_most_recent_session_named_with_key(self):
        self.write("1.json", {"sessionId": "old", "name": "OPS-369 vecchia", "cwd": "/x", "statusUpdatedAt": 1})
        self.write("2.json", {"sessionId": "new", "name": "OPS-369 nuova", "cwd": "/y", "statusUpdatedAt": 5})
        self.write("3.json", {"sessionId": "other", "name": "OPS-3690 altro", "statusUpdatedAt": 9})
        self.write("4.json", "{rotto")
        self.assertEqual(sessions.find_open("OPS-369")["sessionId"], "new")

    def test_exact_name_without_title_matches(self):
        self.write("1.json", {"sessionId": "s", "name": "OPS-369"})
        self.assertEqual(sessions.find_open("OPS-369")["sessionId"], "s")

    def test_none_when_no_sessions(self):
        self.assertIsNone(sessions.find_open("OPS-369"))


class FindClosedTest(TempHomeCase):
    def transcript(self, session_id, title, cwd, mtime):
        import os
        path = self.home / ".claude/projects/p" / ("%s.jsonl" % session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [{"type": "user", "cwd": cwd, "message": {"content": "ciao"}},
                 {"type": "custom-title", "customTitle": title, "sessionId": session_id}]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        os.utime(path, (mtime, mtime))

    def test_most_recent_closed_session_with_key_title(self):
        self.transcript("old", "APP-410 vecchia", "/a", 100)
        self.transcript("new", "APP-410 nuova", "/b", 200)
        self.transcript("other", "APP-4100 altro", "/c", 300)
        found = sessions.find_closed("APP-410")
        self.assertEqual((found["sessionId"], found["cwd"]), ("new", "/b"))

    def test_none_without_titled_transcripts(self):
        self.transcript("x", "jdoe-76", "/a", 100)
        self.assertIsNone(sessions.find_closed("APP-410"))

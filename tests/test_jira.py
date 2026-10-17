import io
import json
import os
import urllib.error
from unittest import mock

from cc_panel import jira
from tests.helpers import TempHomeCase

ADF = {"type": "doc", "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "Prima riga"}]},
    {"type": "bulletList", "content": [{"type": "listItem", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": "punto"}]}]}]},
]}


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


def issue_payload(parent):
    return {"key": "AI-9", "fields": {
        "summary": " Titolo ", "status": {"name": "IN LAVORAZIONE"}, "issuetype": {"name": "Task"},
        "parent": parent, "description": ADF,
        "comment": {"comments": [
            {"author": {"displayName": "A"}, "created": "2026-10-0%dT10:00:00.000+0200" % i, "body": ADF}
            for i in range(1, 6)]},
    }}


class JiraTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self._token = os.environ.pop("JIRA_API_TOKEN", None)

    def tearDown(self):
        if self._token is not None:
            os.environ["JIRA_API_TOKEN"] = self._token
        super().tearDown()

    def test_token_read_from_zshrc(self):
        (self.home / ".zshrc").write_text("alias x=y\nexport JIRA_API_TOKEN='abc'\n")
        self.assertEqual(jira.load_token(), "abc")

    def test_missing_token_raises(self):
        with self.assertRaises(jira.JiraError):
            jira.load_token()

    def test_issue_with_epic_parent(self):
        os.environ["JIRA_API_TOKEN"] = "t"
        parent = {"key": "AI-1", "fields": {"summary": "Epica", "issuetype": {"name": "Epic"}}}
        with mock.patch("urllib.request.urlopen", return_value=response(issue_payload(parent))):
            issue = jira.issue("AI-9")
        self.assertEqual(issue["summary"], "Titolo")
        self.assertEqual((issue["epic"], issue["epic_summary"]), ("AI-1", "Epica"))
        self.assertIn("Prima riga", issue["description"])
        self.assertIn("punto", issue["description"])
        self.assertEqual(len(issue["comments"]), 3)
        self.assertEqual(issue["comments"][-1]["created"][:10], "2026-10-05")

    def test_epic_resolved_through_story_parent(self):
        os.environ["JIRA_API_TOKEN"] = "t"
        story = {"key": "AI-5", "fields": {"summary": "Storia", "issuetype": {"name": "Story"}}}
        grandparent = {"key": "AI-5", "fields": {"parent": {"key": "AI-1", "fields": {
            "summary": "Epica", "issuetype": {"name": "Epic"}}}}}
        with mock.patch("urllib.request.urlopen", side_effect=[response(issue_payload(story)), response(grandparent)]):
            issue = jira.issue("AI-9")
        self.assertEqual(issue["epic"], "AI-1")

    def test_http_401_becomes_jira_error(self):
        os.environ["JIRA_API_TOKEN"] = "t"
        error = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(jira.JiraError) as ctx:
                jira.issue("AI-9")
        self.assertIn("401", str(ctx.exception))

    def test_network_error_becomes_jira_error(self):
        os.environ["JIRA_API_TOKEN"] = "t"
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaises(jira.JiraError):
                jira.issue("AI-9")


class CreateIssueTest(JiraTest):
    def test_payload_with_parent_and_assignee(self):
        os.environ["JIRA_API_TOKEN"] = "t"
        requests = []

        def fake(request, timeout):
            requests.append(request)
            if request.full_url.endswith("/myself"):
                return response({"accountId": "acc-1"})
            return response({"key": "AI-77"})
        with mock.patch("urllib.request.urlopen", side_effect=fake):
            key = jira.create_issue("AI", jira.TASK_TYPE, "Titolo", "Riga uno\nRiga due", parent="AI-1")
        self.assertEqual(key, "AI-77")
        body = json.loads(requests[-1].data)
        self.assertEqual(requests[-1].get_method(), "POST")
        fields = body["fields"]
        self.assertEqual(fields["project"], {"key": "AI"})
        self.assertEqual(fields["issuetype"], {"id": "10005"})
        self.assertEqual(fields["parent"], {"key": "AI-1"})
        self.assertEqual(fields["assignee"], {"accountId": "acc-1"})
        self.assertEqual(fields["description"]["type"], "doc")
        self.assertEqual(len(fields["description"]["content"]), 2)

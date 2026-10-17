"""Lettura dei ticket da Jira Cloud (REST v3, Basic Auth con token personale)."""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from cc_panel import config, paths

TASK_TYPE = "10005"
EPIC_TYPE = "10000"
COMMENT_COUNT = 3
TIMEOUT_SECONDS = 20
_TOKEN_LINE = re.compile(r"^\s*export\s+JIRA_API_TOKEN=(.+?)\s*$")


class JiraError(Exception):
    pass


def load_token():
    token = os.environ.get("JIRA_API_TOKEN")
    if token:
        return token
    # ~/.zshrc non viene letto dalle shell bash: si estrae la sola riga di export.
    try:
        with (paths.home() / ".zshrc").open(encoding="utf-8") as zshrc:
            for line in zshrc:
                match = _TOKEN_LINE.match(line)
                if match:
                    return match.group(1).strip("'\"")
    except OSError:
        pass
    raise JiraError("JIRA_API_TOKEN non trovato (né nell'ambiente né in ~/.zshrc)")


def _get(path, body=None):
    """GET, oppure POST se c'è un corpo JSON."""
    try:
        base_url, email = config.jira_base_url(), config.jira_email()
    except config.ConfigError as error:
        raise JiraError(str(error)) from None
    auth = base64.b64encode(("%s:%s" % (email, load_token())).encode()).decode()
    headers = {"Authorization": "Basic " + auth, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base_url + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        hint = {401: "token scaduto o non valido", 404: "ticket inesistente o non visibile"}.get(error.code, "")
        detail = ""
        try:
            errors = json.load(error)
            detail = "; ".join(errors.get("errorMessages", []) + ["%s: %s" % kv for kv in errors.get("errors", {}).items()])
        except (ValueError, AttributeError, TypeError, KeyError, OSError):
            pass
        raise JiraError(("Jira ha risposto %d %s %s" % (error.code, hint, detail)).strip()) from None
    except (urllib.error.URLError, OSError) as error:
        raise JiraError("Jira non raggiungibile: %s" % getattr(error, "reason", error)) from None


def adf_text(node):
    """Testo semplice da un documento Atlassian Document Format, un blocco per riga."""
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [adf_text(child) for child in node.get("content", [])]
    separator = "\n" if node.get("type") in ("doc", "bulletList", "orderedList", "listItem", "table", "tableRow") else ""
    return separator.join(p for p in parts if p).strip() if separator else "".join(parts)


def _is_epic(issue_ref):
    return issue_ref["fields"]["issuetype"]["name"] == "Epic"


def issue(key):
    data = _get("/rest/api/3/issue/%s?fields=summary,status,issuetype,parent,description,comment" % key)
    fields = data["fields"]
    parent = fields.get("parent")
    epic = None
    if parent and _is_epic(parent):
        epic = parent
    elif parent:
        grandparent = _get("/rest/api/3/issue/%s?fields=parent" % parent["key"]).get("fields", {}).get("parent")
        if grandparent and _is_epic(grandparent):
            epic = grandparent
    comments = (fields.get("comment") or {}).get("comments", [])[-COMMENT_COUNT:]
    return {
        "key": data["key"],
        "summary": fields["summary"].strip(),
        "status": fields["status"]["name"],
        "type": fields["issuetype"]["name"],
        "epic": epic["key"] if epic else None,
        "epic_summary": epic["fields"]["summary"].strip() if epic else None,
        "description": adf_text(fields.get("description")),
        "comments": [{"author": (c.get("author") or {}).get("displayName", "?"), "created": c.get("created", ""),
                      "body": adf_text(c.get("body"))} for c in comments],
        "url": "%s/browse/%s" % (config.jira_base_url(), data["key"]),
    }


def search(jql, fields):
    """Tutte le issue della ricerca JQL, seguendo la paginazione."""
    issues, page_token = [], None
    while True:
        params = {"jql": jql, "fields": ",".join(fields), "maxResults": "100"}
        if page_token:
            params["nextPageToken"] = page_token
        payload = _get("/rest/api/3/search/jql?" + urllib.parse.urlencode(params))
        issues.extend(payload.get("issues", []))
        page_token = payload.get("nextPageToken")
        if not page_token or payload.get("isLast", True):
            return issues


def myself():
    return _get("/rest/api/3/myself")


def _adf(text):
    return {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in text.splitlines() if line]}


def create_issue(project, type_id, summary, description, parent=None):
    """Crea una issue assegnata all'utente e ne restituisce la chiave."""
    fields = {"project": {"key": project}, "issuetype": {"id": type_id}, "summary": summary,
              "description": _adf(description), "assignee": {"accountId": myself()["accountId"]}}
    if parent:
        fields["parent"] = {"key": parent}
    return _get("/rest/api/3/issue", body={"fields": fields})["key"]

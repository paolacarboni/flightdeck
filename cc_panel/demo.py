"""Dati inventati per provare il pannello senza Jira (`cc-panel board --demo`)."""
import time

BASE_URL = "https://example.atlassian.net"


def _item(key, summary, category="indeterminate", session=None, next_step=None, status=None):
    return {"key": key, "summary": summary, "type": "Task",
            "status": status or {"indeterminate": "In Progress", "new": "To Do"}[category],
            "statusCategory": category, "session": session or {"state": "none"}, "nextStep": next_step}


def _repo(name, branch, dirty=0, ahead=0, days=1, sessions=3):
    return {"path": "~/code/%s" % name, "name": name, "branch": branch, "dirty": dirty, "ahead": ahead,
            "lastCommitDays": days, "sessions": sessions}


def model(now=None):
    now = time.time() if now is None else now
    epics = [
        {"key": "ORION-12", "summary": "🛰️ Navigation core rewrite", "status": "In Progress",
         "progress": {"done": 14, "indeterminate": 4, "new": 6},
         "items": [
             _item("ORION-41", "Replace star tracker driver with async API",
                   session={"state": "open", "status": "waiting", "sessionId": "demo-1"},
                   next_step="Answer Claude about the retry policy, then run the hardware-in-the-loop suite"),
             _item("ORION-44", "Kalman filter: tune process noise for docking",
                   session={"state": "open", "status": "idle", "sessionId": "demo-2"}),
             _item("ORION-47", "Course-correction planner benchmarks",
                   session={"state": "closed", "sessionId": "demo-3"},
                   next_step="Compare the new planner against last week's baseline"),
             _item("ORION-52", "Document the navigation state machine", "new"),
         ],
         "repos": [_repo("nav-core", "feature/ORION-41-async-tracker", dirty=4, ahead=2, days=0),
                   _repo("flight-sim", "main", days=3)]},
        {"key": "HELIX-4", "summary": "🫁 Life support telemetry", "status": "In Progress",
         "progress": {"done": 9, "indeterminate": 2, "new": 3},
         "items": [
             _item("HELIX-18", "Stream O₂ scrubber metrics to the ops dashboard",
                   session={"state": "open", "status": "idle", "sessionId": "demo-4", "staleDays": 2}),
             _item("HELIX-21", "Alert thresholds for cabin pressure drift"),
         ],
         "repos": [_repo("telemetry-gateway", "feature/HELIX-18-scrubber", dirty=1, days=2)]},
        {"key": "ATLAS-3", "summary": "🔌 Docking API v2", "status": "In Progress",
         "progress": {"done": 2, "indeterminate": 1, "new": 7},
         "items": [_item("ATLAS-9", "Versioned handshake for third-party modules",
                         next_step="Draft the OpenAPI spec and share it with the module vendors")],
         "repos": [_repo("docking-api", "feature/ATLAS-9-handshake", ahead=1, days=1)]},
        {"key": "VEGA-9", "summary": "⛽ Fuel cost dashboard", "status": "In Progress",
         "progress": {"done": 18, "indeterminate": 1, "new": 1},
         "items": [_item("VEGA-31", "Monthly burn report export to CSV")],
         "repos": [_repo("fuel-insights", "main", days=6)]},
        {"key": "NOVA-7", "summary": "🧑‍🚀 Crew onboarding portal", "status": "To Do",
         "progress": {"done": 0, "indeterminate": 0, "new": 5},
         "items": [_item("NOVA-2", "Wireframes for the first-day checklist", "new")],
         "repos": []},
    ]
    no_epic = [_item("OPS-77", "Renew the ground-station TLS certificates"),
               _item("OPS-80", "Quarterly access review", "new")]
    proposals = [
        {"sessionId": "demo-p1", "sessionIds": ["demo-p1", "demo-p2"], "title": "Automate the flight-sim nightly regression",
         "why": "Script, CI job and flaky-test report written across two sessions.", "cwd": "~/code/flight-sim",
         "folder": "flight-sim", "hoursAgo": 20, "epicKey": "ORION-12", "epicSummary": "🛰️ Navigation core rewrite"},
        {"sessionId": "demo-p3", "sessionIds": ["demo-p3"], "title": "Prototype the anomaly detector for O₂ readings",
         "why": "Notebook, feature extraction and a first model with evaluation.", "cwd": "~/code/telemetry-gateway",
         "folder": "telemetry-gateway", "hoursAgo": 50, "epicKey": "HELIX-4", "epicSummary": "🫁 Life support telemetry"},
        {"sessionId": "demo-p4", "sessionIds": ["demo-p4", "demo-p5", "demo-p6"], "title": "Build the cargo manifest validator",
         "why": "New CLI with schema checks and tests; not tracked anywhere yet.", "cwd": "~/code/cargo-tools",
         "folder": "cargo-tools", "hoursAgo": 70, "epicKey": None, "epicSummary": None},
    ]
    items = [i for e in epics for i in e["items"]] + no_epic
    return {
        "baseUrl": BASE_URL, "updatedAt": int(now), "myOpenJql": "assignee = currentUser() AND statusCategory != Done",
        "summary": {"inProgress": sum(1 for i in items if i["statusCategory"] == "indeterminate"),
                    "waitingSessions": sum(1 for i in items if i["session"].get("status") == "waiting"),
                    "staleSessions": sum(1 for i in items if i["session"].get("staleDays"))},
        "epics": epics, "noEpic": no_epic, "proposals": proposals,
    }

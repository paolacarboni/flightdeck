"""Modello del pannello: epiche su cui lavoro, con attività Jira, repo, sessioni e riprese."""
import json
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cc_panel import config, digest, folders, gitstate, history, jira, notes, paths, repoindex, sessions, tracking

MY_OPEN_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
MAX_REPOS = 4
CATEGORIES = ("done", "indeterminate", "new")
MAX_PROPOSALS = 5
STALE_HOURS = 24


def _keys_jql(keys):
    return ", ".join(sorted(keys))


def _is_epic(ref):
    return ref["fields"]["issuetype"]["name"] == "Epic"


def _epic_of(mine):
    """Chiave dell'epica di ogni attività, risalendo da sotto-task e storie."""
    epic_of, via_parent = {}, {}
    for issue in mine:
        parent = issue["fields"].get("parent")
        if _is_epic(issue):
            epic_of[issue["key"]] = issue["key"]
        elif parent and _is_epic(parent):
            epic_of[issue["key"]] = parent["key"]
        elif parent:
            via_parent[issue["key"]] = parent["key"]
    if via_parent:
        grand = {}
        for parent in jira.search("key in (%s)" % _keys_jql(set(via_parent.values())), ["parent"]):
            # Jira omette "fields" quando l'unico campo richiesto è vuoto.
            gp = parent.get("fields", {}).get("parent")
            if gp and _is_epic(gp):
                grand[parent["key"]] = gp["key"]
        for key, parent_key in via_parent.items():
            if parent_key in grand:
                epic_of[key] = grand[parent_key]
    return epic_of


def _hours_since(session, now):
    updated = session.get("statusUpdatedAt")
    return (now - updated / 1000.0) / 3600 if updated else None


def _session_of(key, opened, indexed, linked, now):
    """Sessione dell'attività: aperta, altrimenti l'ultima chiusa; per nome o per collegamento."""
    session = sessions.find_open(key, opened) or max(
        (s for s in opened if linked.get(s.get("sessionId")) == key),
        key=lambda s: s.get("statusUpdatedAt") or 0, default=None)
    if session:
        result = {"state": "open", "status": session.get("status"), "sessionId": session.get("sessionId")}
        hours = _hours_since(session, now)
        if hours is not None and hours >= STALE_HOURS:
            result["staleDays"] = int(hours // 24)
        return result
    closed = sessions.find_closed(key, indexed)
    if not closed:
        mine = [s for s in indexed if linked.get(s["sessionId"]) == key]
        closed = max(mine, key=lambda s: s["mtime"], default=None)
    return {"state": "closed", "sessionId": closed["sessionId"]} if closed else {"state": "none"}


def _spawn_digest():
    """Avvia `cc-panel digest` staccato dal pannello: la valutazione con Claude richiede minuti."""
    cli = Path(__file__).resolve().parent.parent / "bin" / "cc-panel"
    subprocess.Popen([str(cli), "digest"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def _proposals(indexed, linked, ignored, epic_summaries, now):
    """Temi di lavoro di valore senza ticket, già formulati come ticket dal digest."""
    found = digest.candidates(indexed, linked, ignored, now)
    if digest.pending(indexed, linked, ignored, now):
        _spawn_digest()
    eligible = {s["sessionId"]: s for s, _ in digest.ungrouped(found, digest.load())}
    proposals = []
    for group in digest.groups():
        sessions_ = sorted((eligible[sid] for sid in group["sessionIds"] if sid in eligible), key=lambda s: -s["mtime"])
        if not sessions_:
            continue
        latest = sessions_[0]
        cwd = Path(latest["cwd"]) if latest["cwd"] else None
        epic_key = group.get("epicKey") if group.get("epicKey") in epic_summaries else None
        proposals.append({
            "sessionId": latest["sessionId"], "sessionIds": [s["sessionId"] for s in sessions_],
            "title": group["title"], "why": group.get("why"), "cwd": latest["cwd"],
            "folder": None if cwd is None else "~" if cwd == paths.home() else cwd.name,
            "hoursAgo": (now - latest["mtime"]) / 3600, "epicKey": epic_key,
            "epicSummary": epic_summaries.get(epic_key)})
    return proposals[:MAX_PROPOSALS]


def _next_step(key):
    note = paths.ticket_note(key)
    try:
        return notes.next_step(note.read_text(encoding="utf-8")) if note.exists() else None
    except OSError:
        return None


def _item(issue, opened, indexed, linked, now):
    fields = issue["fields"]
    return {"key": issue["key"], "summary": fields["summary"].strip(), "type": fields["issuetype"]["name"],
            "status": fields["status"]["name"], "statusCategory": fields["status"]["statusCategory"]["key"],
            "session": _session_of(issue["key"], opened, indexed, linked, now), "nextStep": _next_step(issue["key"])}


def _repos(epic_keys, indexed):
    """Cartelle in cui si è lavorato sull'epica, raggruppate per repo git.

    Ogni sessione pesa per la frazione delle chiavi citate che appartengono all'epica: una
    sessione dedicata vale 1, una che passa in rassegna molti ticket vale poco.
    """
    scores, counts = Counter(), Counter()
    for session in indexed:
        shared = session["keys"] & epic_keys
        if session["cwd"] and shared:
            scores[session["cwd"]] += len(shared) / len(session["keys"])
            counts[session["cwd"]] += 1
    for key in epic_keys:
        remembered = folders.remembered(key)
        if remembered:
            scores[str(remembered)] += 1
            counts[str(remembered)] += 1
    by_root_score, by_root_count = Counter(), Counter()
    session_counts = dict(folders.relocated_counts(counts))
    for folder, score in folders.relocated_counts(scores):
        # Le cartelle che non sono repo (es. contenitori di più repo) restano come cartelle di progetto.
        root = gitstate.root(folder) or folder
        by_root_score[root] += score
        by_root_count[root] += session_counts.get(folder, 0)
    repos = []
    for root, _ in by_root_score.most_common(MAX_REPOS):
        state = gitstate.status(root) if (root / ".git").exists() else None
        state = state or {"branch": None, "dirty": None, "ahead": None, "lastCommitDays": None}
        repos.append(dict(state, path=str(root), name=root.name, sessions=by_root_count[root]))
    return repos


def _in_progress_first(items):
    return sorted(items, key=lambda i: i["statusCategory"] != "indeterminate")


def _build():
    mine = jira.search(MY_OPEN_JQL, ["summary", "status", "issuetype", "parent"])
    epic_of = _epic_of(mine)
    now = time.time()
    linked, ignored = tracking.links(), tracking.ignored()
    opened = sessions.open_sessions()
    # Una sessione collegata a un ticket conta come se lo citasse (cartelle dell'epica).
    indexed = [dict(s, keys=s["keys"] | ({linked[s["sessionId"]]} if s["sessionId"] in linked else set()))
               for s in history.index()]
    epics, children = {}, {}
    if epic_of:
        epic_keys = set(epic_of.values())
        # Jira restituisce al massimo 100 issue per pagina: dettagli e figli di ogni epica in parallelo.
        with ThreadPoolExecutor(max_workers=len(epic_keys) + 1) as pool:
            details = pool.submit(jira.search, "key in (%s)" % _keys_jql(epic_keys), ["summary", "status"])
            kids = [pool.submit(jira.search, "parent in (%s)" % key, ["status", "parent"]) for key in sorted(epic_keys)]
        for epic in details.result():
            epics[epic["key"]] = {"key": epic["key"], "summary": epic["fields"]["summary"].strip(),
                                  "status": epic["fields"]["status"]["name"],
                                  "progress": dict.fromkeys(CATEGORIES, 0), "items": []}
            children[epic["key"]] = {epic["key"]}
        for child in (c for future in kids for c in future.result()):
            epic_key = child["fields"]["parent"]["key"]
            category = child["fields"]["status"]["statusCategory"]["key"]
            if epic_key in epics and category in CATEGORIES:
                epics[epic_key]["progress"][category] += 1
                children[epic_key].add(child["key"])
    no_epic = []
    for issue in mine:
        if _is_epic(issue):
            continue
        epic = epics.get(epic_of.get(issue["key"]))
        (epic["items"] if epic else no_epic).append(_item(issue, opened, indexed, linked, now))
    for key, epic in epics.items():
        epic["items"] = _in_progress_first(epic["items"])
        epic["repos"] = _repos(children[key] | {i["key"] for i in epic["items"]}, indexed)
    all_items = no_epic + [i for e in epics.values() for i in e["items"]]

    def weight(epic):
        active = sum(1 for i in epic["items"] if i["statusCategory"] == "indeterminate")
        return (-active, -len(epic["items"]), epic["key"])

    return {"baseUrl": config.jira_base_url(), "updatedAt": int(time.time()),
            "summary": {"inProgress": sum(1 for i in all_items if i["statusCategory"] == "indeterminate"),
                        "waitingSessions": sum(1 for s in opened if s.get("status") == "waiting"),
                        "staleSessions": sum(1 for s in opened if (_hours_since(s, now) or 0) >= STALE_HOURS)},
            "epics": sorted(epics.values(), key=weight), "noEpic": _in_progress_first(no_epic),
            "proposals": _proposals(indexed, linked, ignored, {k: e["summary"] for k, e in epics.items()}, now),
            "myOpenJql": MY_OPEN_JQL}


def _safe_base_url():
    try:
        return config.jira_base_url()
    except config.ConfigError:
        return ""


def _cache_file():
    return paths.home() / ".claude/cc-panel/board.json"


def build():
    if repoindex.is_stale(repoindex.load(), time.time()):
        repoindex.spawn_build()
    try:
        model = _build()
    except jira.JiraError as error:
        try:
            model = json.loads(_cache_file().read_text(encoding="utf-8"))
            model["stale"] = True
        except (OSError, ValueError):
            model = {"baseUrl": _safe_base_url(), "updatedAt": None,
                     "summary": {"inProgress": 0, "waitingSessions": 0, "staleSessions": 0},
                     "epics": [], "noEpic": [], "proposals": [], "myOpenJql": MY_OPEN_JQL}
        model["error"] = str(error)
        return model
    target = _cache_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
    return model


def render_text(model):
    lines = []
    if model.get("error"):
        lines.append("! %s" % model["error"])
    for epic in model["epics"]:
        progress = epic["progress"]
        lines.append("%s  %s  (%d attività, %d/%d completate)" % (
            epic["key"], epic["summary"], len(epic["items"]), progress["done"], sum(progress.values())))
        for item in epic["items"]:
            lines.append("    %-9s %-15s %s" % (item["key"], item["status"], item["summary"]))
        for repo in epic["repos"]:
            lines.append("    ↳ %s (%s)" % (repo["name"], repo["branch"] or "?"))
    if model["noEpic"]:
        lines.append("Senza epica")
        lines += ["    %-9s %-15s %s" % (i["key"], i["status"], i["summary"]) for i in model["noEpic"]]
    return "\n".join(lines)

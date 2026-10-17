"""Lavoro non tracciato: collegare le sessioni Claude ai ticket, crearne di nuovi, ignorarle."""
from cc_panel import config, history, jira, keys, paths, sessions, state, terminal


class TrackingError(Exception):
    pass


def links():
    return dict(state.load().get("links", {}))


def ignored():
    return set(state.load().get("ignored", []))


def link(session_id, key):
    if not keys.is_key(key):
        raise TrackingError("Chiave ticket non valida: %s" % key)
    current = state.load()
    current.setdefault("links", {})[session_id] = key
    state.save(current)


def ignore(session_id):
    current = state.load()
    current["ignored"] = sorted(set(current.get("ignored", [])) | {session_id})
    state.save(current)


def label(session):
    return session.get("title") or session.get("name") or session.get("firstPrompt") or session["sessionId"][:8]


def find_session(session_id):
    for session in sessions.open_sessions():
        if session.get("sessionId") == session_id:
            indexed = next((s for s in history.index() if s["sessionId"] == session_id), {})
            return dict(indexed, **session)
    for session in history.index():
        if session["sessionId"] == session_id:
            return session
    raise TrackingError("Sessione non trovata: %s" % session_id)


def track(session_ids, epic=None, new_epic=False, summary=None, project=None):
    """Crea su Jira un Task sotto `epic` (o una nuova Epic) per una o più sessioni e le collega."""
    if isinstance(session_ids, str):
        session_ids = [session_ids]
    found = [find_session(sid) for sid in session_ids]
    summary = summary or label(found[0])
    description = "Lavoro svolto in sessioni Claude Code e tracciato con cc-panel.\n" + "\n".join(
        "Sessione: %s (%s) — cartella %s" % (label(s), sid, s.get("cwd") or "?") for sid, s in zip(session_ids, found))
    if new_epic:
        project = project or config.default_project()
        if not project:
            raise TrackingError("Per creare un'epica serve «default_project» nella configurazione")
        key = jira.create_issue(project, jira.EPIC_TYPE, summary, description)
    elif epic and keys.is_key(epic):
        key = jira.create_issue(epic.split("-")[0], jira.TASK_TYPE, summary, description, parent=epic)
    else:
        raise TrackingError("Serve un'epica valida (--epic KEY) oppure --new-epic")
    for sid in session_ids:
        link(sid, key)
    return key


def resume(session_id, launch=terminal.launch):
    session = find_session(session_id)
    launch(terminal.resume_command(session.get("cwd") or str(paths.home()), session_id))

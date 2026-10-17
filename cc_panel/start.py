"""`cc-panel start`: riprende la sessione aperta sul ticket o ne apre una nuova contestualizzata."""
import sys
from pathlib import Path

from cc_panel import brief, folders, jira, notes, paths, sessions, terminal

NAME_SUMMARY_LIMIT = 60
RESUME_ENTRIES = 2


def _proposals(key, epic):
    proposals = folders.suggest(key, epic)
    return proposals + [repo for repo in folders.repos() if repo not in proposals]


def _choose_folder(proposals, ask, out):
    for index, folder in enumerate(proposals, 1):
        print("  %2d) %s" % (index, folder), file=out)
    while True:
        answer = ask("Cartella [invio = 1, numero o percorso]: ").strip()
        if not answer and proposals:
            return proposals[0]
        if answer.isdigit() and 1 <= int(answer) <= len(proposals):
            return proposals[int(answer) - 1]
        candidate = Path(answer).expanduser()
        if answer and candidate.is_dir():
            return candidate.absolute()
        print("Scelta non valida: %s" % (answer or "(vuota)"), file=out)


def session_name(key, summary):
    """«<chiave> <titolo>» con il titolo tagliato all'ultima parola intera entro il limite."""
    if len(summary) > NAME_SUMMARY_LIMIT:
        summary = summary[:NAME_SUMMARY_LIMIT + 1].rsplit(" ", 1)[0]
    return ("%s %s" % (key, summary.rstrip(" ([{-–—:,;"))).strip()


def _resume_entries(key):
    note = paths.ticket_note(key)
    return notes.latest_entries(note.read_text(encoding="utf-8"), RESUME_ENTRIES) if note.exists() else []


def run(key, new=False, dir_=None, auto=False, ask=input, launch=terminal.launch, out=sys.stdout):
    try:
        return _run(key, new, dir_, auto, ask, launch, out)
    except terminal.LaunchError as error:
        print(str(error), file=sys.stderr)
        return 1


def _run(key, new, dir_, auto, ask, launch, out):
    if not new:
        session = sessions.find_open(key)
        state = "aperta"
        if not session:
            session, state = sessions.find_closed(key), "chiusa"
        if session:
            cwd = session.get("cwd") or str(paths.home())
            print("Ultima sessione %s su %s: «%s». La riprendo (--new per una sessione nuova)." % (
                state, key, session.get("name")), file=out)
            launch(terminal.resume_command(cwd, session["sessionId"]))
            return 0
    try:
        issue = jira.issue(key)
    except jira.JiraError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("%s — %s" % (key, issue["summary"]), file=out)
    if dir_:
        folder = Path(dir_).expanduser().absolute()
        if not folder.is_dir():
            print("Cartella inesistente: %s" % folder, file=sys.stderr)
            return 1
    elif auto:
        proposals = _proposals(key, issue["epic"])
        if not proposals:
            print("Nessuna cartella da proporre per %s: usa --dir <percorso>." % key, file=sys.stderr)
            return 1
        folder = proposals[0]
    else:
        try:
            folder = _choose_folder(_proposals(key, issue["epic"]), ask, out)
        except EOFError:
            folder = folders.remembered(key)
            if not folder:
                print("Nessun terminale interattivo per scegliere la cartella: rilancia con --dir <percorso>.",
                      file=sys.stderr)
                return 1
            print("\nNessun terminale interattivo: uso la cartella ricordata.", file=out)
    folders.remember(key, folder)
    brief_file = paths.briefs_dir() / ("%s.md" % key)
    brief_file.parent.mkdir(parents=True, exist_ok=True)
    brief_file.write_text(brief.compose(issue, _resume_entries(key)), encoding="utf-8")
    name = session_name(key, issue["summary"])
    launch(terminal.new_session_command(folder, name, brief_file))
    print("Sessione «%s» avviata in %s" % (name, folder), file=out)
    return 0

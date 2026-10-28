"""`cc-panel start`: riprende la sessione aperta sul ticket o ne apre una nuova contestualizzata."""
import sys
import time
from pathlib import Path

from cc_panel import brief, folders, jira, notes, paths, placement, sessions, terminal

NAME_SUMMARY_LIMIT = 60
RESUME_ENTRIES = 2


def _from_ticket(issue, rank, dense, out):
    """Cartelle scelte dal contesto del ticket, con l'evidenza."""
    started = time.monotonic()
    options = {"dense": dense} if dense else {}
    try:
        ranked = rank(issue, warn=lambda message: print(message, file=out), **options)
    except Exception as error:  # noqa: BLE001 — le proposte non devono mai impedire di aprire la sessione
        print("Proposte dal ticket non disponibili: %s: %s" % (type(error).__name__, error), file=out)
        return []
    if ranked:
        elapsed = ("%.1f" % (time.monotonic() - started)).replace(".", ",")
        print("Cartelle proposte dal ticket (%s s):" % elapsed, file=out)
    return ranked


def _proposals(key, issue, ranking, out):
    """Cartelle in ordine (prima quelle dal ticket, se è nuovo) ed evidenze di quelle proposte dal ticket.
    `ranking` = (rank, processo denso già avviato o None), oppure None per un ticket già lavorato."""
    ranked = _from_ticket(issue, ranking[0], ranking[1], out) if ranking else []
    proposals = [folder for folder, _ in ranked]
    proposals += [folder for folder in folders.suggest(key, issue["epic"]) if folder not in proposals]
    return proposals + [repo for repo in folders.repos() if repo not in proposals], dict(ranked)


def _print_proposals(proposals, evidence, out):
    for index, folder in enumerate(proposals, 1):
        why = evidence.get(folder)
        print("  %2d) %s%s" % (index, folder, " — %s" % why if why else ""), file=out)


def _choose_folder(proposals, ask, out, evidence=None):
    _print_proposals(proposals, evidence or {}, out)
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


def run(key, new=False, dir_=None, auto=False, ask=input, launch=terminal.launch, out=sys.stdout,
        rank=placement.rank, warm_up=placement.warm_up):
    try:
        return _run(key, new, dir_, auto, ask, launch, out, rank, warm_up)
    except terminal.LaunchError as error:
        print(str(error), file=sys.stderr)
        return 1


def _run(key, new, dir_, auto, ask, launch, out, rank, warm_up):
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
    ranking = None
    if not dir_ and not folders.remembered(key):
        # Il lato denso carica il modello mentre si leggono la storia delle sessioni e il ticket da Jira;
        # se la storia cita già il ticket le proposte non servono e il processo si chiude.
        dense = warm_up()
        if not folders.from_history(key):
            ranking = (rank, dense)
        elif dense:
            dense.close()
    try:
        return _open(key, dir_, auto, ask, launch, out, ranking)
    finally:
        if ranking and ranking[1]:
            ranking[1].close()


def _open(key, dir_, auto, ask, launch, out, ranking):
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
        proposals, evidence = _proposals(key, issue, ranking, out)
        if not proposals:
            print("Nessuna cartella da proporre per %s: usa --dir <percorso>." % key, file=sys.stderr)
            return 1
        _print_proposals(proposals[:len(evidence)], evidence, out)
        folder = proposals[0]
    else:
        try:
            proposals, evidence = _proposals(key, issue, ranking, out)
            folder = _choose_folder(proposals, ask, out, evidence)
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

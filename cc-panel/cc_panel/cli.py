"""Punto di ingresso di cc-panel."""
import argparse
import json
import sys
from datetime import datetime

from pathlib import Path

from cc_panel import board, demo, digest, jira, keys, notes, paths, repoindex, semantic, start, terminal, tracking


def build_parser():
    parser = argparse.ArgumentParser(prog="cc-panel", description="Riprendi il lavoro dai ticket Jira.")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("start", help="apre o riprende la sessione Claude di un ticket")
    start.add_argument("key")
    start.add_argument("--new", action="store_true", help="nuova sessione anche se una è già aperta")
    start.add_argument("--dir", help="cartella di lavoro, senza proposta")
    start.add_argument("--auto", action="store_true", help="nessuna domanda: usa la prima cartella proposta")
    park = sub.add_parser("park", help="aggiunge una nota di ripresa (markdown da stdin)")
    park.add_argument("key")
    open_cmd = sub.add_parser("open", help="apre una cartella nel terminale (Ghostty se installato)")
    open_cmd.add_argument("folder")
    link = sub.add_parser("link", help="collega una sessione Claude a un ticket")
    link.add_argument("session")
    link.add_argument("key")
    ignore = sub.add_parser("ignore", help="scarta una o più sessioni dalle proposte")
    ignore.add_argument("session", nargs="+")
    track = sub.add_parser("track", help="crea su Jira il task (o l'epica) di una o più sessioni e le collega")
    track.add_argument("session", nargs="+")
    target = track.add_mutually_exclusive_group(required=True)
    target.add_argument("--epic", help="epica sotto cui creare il task")
    target.add_argument("--new-epic", action="store_true", help="crea una nuova epica nel progetto default_project")
    track.add_argument("--summary", help="titolo (default: nome o primo messaggio della sessione)")
    resume = sub.add_parser("resume", help="riprende una sessione Claude per id")
    resume.add_argument("session")
    sub.add_parser("digest", help="valuta con Claude le sessioni senza ticket (in background dal pannello)")
    sub.add_parser("index", help="indicizza i repo per proporre la cartella dei ticket nuovi (in background dal pannello)")
    setup = sub.add_parser("semantic-setup", help="installa venv e modello della ricerca semantica delle cartelle")
    setup.add_argument("--from", dest="source", help="cartella con i file del modello già scaricati (verificati)")
    board_cmd = sub.add_parser("board", help="epiche con attività, repo, sessioni e riprese")
    board_cmd.add_argument("--json", action="store_true", help="modello completo in JSON (per il pannello)")
    board_cmd.add_argument("--demo", action="store_true", help="dati inventati, senza Jira (per provare il pannello)")
    return parser


def park(key):
    entry = sys.stdin.read()
    if not entry.strip():
        print("Nota di ripresa vuota: niente da salvare.", file=sys.stderr)
        return 1
    note = paths.ticket_note(key)
    text = note.read_text(encoding="utf-8") if note.exists() else notes.new_note(key)
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(notes.add_entry(text, entry, datetime.now().strftime("%Y-%m-%d %H:%M")), encoding="utf-8")
    print("Ripresa salvata in %s" % note)
    return 0


def _session_command(args):
    try:
        if args.command == "link":
            tracking.link(args.session, args.key)
            print("Sessione collegata a %s" % args.key)
        elif args.command == "ignore":
            for session_id in args.session:
                tracking.ignore(session_id)
            print("Proposta scartata")
        elif args.command == "track":
            key = tracking.track(args.session, epic=args.epic, new_epic=args.new_epic, summary=args.summary)
            print("Creato %s e collegata la sessione" % key)
        else:
            tracking.resume(args.session)
            print("Sessione ripresa")
    except (tracking.TrackingError, jira.JiraError, terminal.LaunchError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def index():
    try:
        meta = repoindex.build()
    except repoindex.VectorsError as error:
        print("Indice salvato, ma vettori non calcolati: %s. Le proposte usano solo le parole." % error,
              file=sys.stderr)
        return 1
    if meta is None:
        print("Indicizzazione già in corso.")
        return 0
    print("Indice: %d repo, %d frammenti." % (len(meta["candidates"]), len(meta["chunks"])))
    if semantic.python() is None:
        print("Ricerca semantica non installata: solo parole. Per attivarla: cc-panel semantic-setup")
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "index":
        return index()
    if args.command == "semantic-setup":
        return semantic.setup(source=args.source)
    if args.command == "digest":
        print("Sessioni valutate: %d" % digest.run())
        return 0
    if args.command == "board":
        model = demo.model() if args.demo else board.build()
        print(json.dumps(model, ensure_ascii=False) if args.json else board.render_text(model))
        return 0
    if args.command in ("link", "ignore", "track", "resume"):
        return _session_command(args)
    if args.command == "open":
        folder = Path(args.folder).expanduser()
        if not folder.is_dir():
            print("Cartella inesistente: %s" % folder, file=sys.stderr)
            return 1
        try:
            terminal.launch(terminal.open_folder_command(folder))
        except terminal.LaunchError as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    if not keys.is_key(args.key):
        print("Chiave ticket non valida: %s" % args.key, file=sys.stderr)
        return 1
    if args.command == "park":
        return park(args.key)
    try:
        return start.run(args.key, new=args.new, dir_=args.dir, auto=args.auto)
    except (KeyboardInterrupt, EOFError):
        print("\nAnnullato.", file=sys.stderr)
        return 1

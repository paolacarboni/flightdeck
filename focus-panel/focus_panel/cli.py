"""Punto di ingresso di focus-panel."""
import argparse
import json
import sys
import time

from focus_panel import deadlines, store, view


def _now():
    return time.time()


def build_parser():
    parser = argparse.ArgumentParser(prog="focus-panel", description="Frog, time box e scadenze.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="stato in JSON (per il pannello)")
    add = sub.add_parser("add", help="nuova voce: verbo + oggetto, con durata stimata")
    add.add_argument("text", nargs="+")
    add.add_argument("-m", "--minutes", type=int, required=True)
    add.add_argument("--when", choices=store.WHEN, default="oggi")
    add.add_argument("--due", help="scadenza AAAA-MM-GG")
    add.add_argument("--frog", action="store_true")
    for name, text in (("frog", "il frog del suo giorno"), ("drop", "elimina la voce")):
        sub.add_parser(name, help=text).add_argument("id", type=int)
    move = sub.add_parser("move", help="sposta su oggi, domani o nel parcheggio")
    move.add_argument("id", type=int)
    move.add_argument("when", choices=store.WHEN)
    start = sub.add_parser("start", help="apre il time box su una voce di oggi")
    start.add_argument("id", type=int)
    start.add_argument("-m", "--minutes", type=int)
    sub.add_parser("extend", help="proroga unica di %d minuti" % store.EXTENSION_MINUTES)
    sub.add_parser("stop", help="chiude il box senza segnare fatta la voce")
    done = sub.add_parser("done", help="segna fatta la voce (default: quella del box)")
    done.add_argument("id", type=int, nargs="?")
    sub.add_parser("sync", help="legge le scadenze da Jira")
    return parser


def _mutate(args, now):
    state = store.load(now)
    if args.command == "add":
        item = store.add(state, " ".join(args.text), args.minutes, args.when, args.due, args.frog, now)
        message = "Aggiunta %d: %s" % (item["id"], item["text"])
    elif args.command == "frog":
        message = "Frog: %s" % store.set_frog(state, args.id, now)["text"]
    elif args.command == "move":
        message = "Spostata: %s" % store.move(state, args.id, args.when, now)["text"]
    elif args.command == "drop":
        message = "Eliminata: %s" % store.drop(state, args.id)["text"]
    elif args.command == "start":
        box = store.start(state, args.id, args.minutes, now)
        message = "Box di %d′: %s" % (box["minutes"], store.find(state, args.id)["text"])
    elif args.command == "extend":
        store.extend(state, now)
        message = "Prorogato di %d′, ultima volta" % store.EXTENSION_MINUTES
    elif args.command == "stop":
        message = "Box chiuso: %s" % store.find(state, store.stop(state, now)["itemId"])["text"]
    else:
        message = "Fatto: %s" % store.done(state, args.id, now)["text"]
    store.save(state)
    return message


def main(argv=None):
    args = build_parser().parse_args(argv)
    now = _now()
    if args.command == "show":
        print(json.dumps(view.show(now), ensure_ascii=False))
        return 0
    if args.command == "sync":
        cache = deadlines.sync(now=now)
        if cache.get("error"):
            print(cache["error"], file=sys.stderr)
            return 1
        print("Scadenze Jira: %d" % len(cache["items"]))
        return 0
    try:
        print(_mutate(args, now))
    except store.FocusError as error:
        print(error, file=sys.stderr)
        return 1
    return 0

"""Punto di ingresso di news-panel."""
import argparse
import json
import sys

from news_panel import edition


def build_parser():
    parser = argparse.ArgumentParser(prog="news-panel", description="Rassegna quotidiana su AI, LLM e tecnologia.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="edizione in cache in JSON (per il pannello); avvia la raccolta se manca quella di oggi")
    sub.add_parser("fetch", help="raccoglie le notizie e prepara l'edizione di oggi con Claude Haiku")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "fetch":
        data = edition.run()
        print("Edizione %s: %d notizie, %d temi" % (data.get("edition", "-"), data.get("count", 0), len(data.get("topics", []))))
        if data.get("error"):
            print(data["error"], file=sys.stderr)
        return 0 if data.get("count") else 1
    print(json.dumps(edition.show(), ensure_ascii=False))
    return 0

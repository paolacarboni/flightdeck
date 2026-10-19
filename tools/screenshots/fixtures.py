"""Dati inventati per gli screenshot: stampa un JSON con l'output demo di ogni pannello e il menu della barra.

Uso (dalla radice del repository): /usr/bin/python3 tools/screenshots/fixtures.py > fixtures.json
Nessun dato reale: cc-panel usa il suo `board --demo`, il resto è scritto qui sotto.
"""
import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "cc-panel"), str(ROOT / "harlock-bar")]

from cc_panel import demo  # noqa: E402
from harlock_bar import menu  # noqa: E402

# Martedì mattina, ore 10:40: giornata in corso, un box attivo.
NOW = datetime(2026, 10, 20, 10, 40).timestamp()
DAY = "2026-10-20"
JIRA = demo.BASE_URL


def _item(id_, text, minutes, frog=False, done=False, day=DAY):
    return {"id": id_, "text": text, "minutes": minutes, "day": day, "frog": frog, "due": None,
            "doneAt": NOW - 3600 if done else None, "created": NOW - 86400}


def focus():
    today = [_item(1, "Write the release notes draft", 45, frog=True, done=True),
             _item(2, "Review the cargo validator PR", 60),
             _item(3, "Plan the telemetry dashboard", 30)]
    box = {"itemId": 2, "start": NOW - 41 * 60, "minutes": 60, "extended": False, "end": NOW + 19 * 60,
           "remaining": 19 * 60 - 20, "phase": "run", "text": today[1]["text"]}
    deadlines = [
        {"source": "jira", "key": "OPS-212", "title": "Rotate the staging certificates", "due": "2026-10-19",
         "url": JIRA + "/browse/OPS-212", "days": -1},
        {"source": "local", "key": None, "title": "Send the quarterly summary", "due": DAY, "url": None, "days": 0},
        {"source": "jira", "key": "WEB-88", "title": "Accessibility pass on the onboarding flow", "due": "2026-10-23",
         "url": JIRA + "/browse/WEB-88", "days": 3},
    ]
    return {"now": NOW, "today": today, "tomorrow": [_item(4, "Pair on the cache migration", 90, day="2026-10-21")],
            "parked": [_item(5, "Clean up old feature flags", 30, day=None)], "frogFirst": False, "planMode": False,
            "tomorrowFrog": False, "box": box, "overToday": 0, "doneToday": 1, "maxPerDay": 3,
            "deadlines": deadlines, "jiraError": None, "syncing": False}


def _news(title, source, area, score=None, summary="", why=None):
    item = {"title": title, "url": "https://example.com/news", "published": NOW - 5 * 3600, "summary": summary,
            "score": score, "commentsUrl": None, "source": source, "area": area}
    if why:
        item["why"] = why
    return item


def news():
    topics = [
        {"title": "Agents that run their own test suites", "area": "AI", "heat": 5,
         "summary": "Several teams report coding agents that write, run and fix tests in a loop, with fewer regressions.",
         "items": [_news("Self-testing agents in practice", "Hacker News", "AI", 812),
                   _news("A benchmark for agentic test repair", "Hugging Face", "RICERCA", 240)]},
        {"title": "Small open models on laptops", "area": "LLM", "heat": 4,
         "summary": "New quantised releases make 8B-class models usable offline for code review and search.",
         "items": [_news("Running an 8B model on a laptop, measured", "Lobsters", "LLM", 96)]},
        {"title": "Prompt caching gets cheaper", "area": "TECH", "heat": 3,
         "summary": "Providers cut prices for cached context: long system prompts become affordable.",
         "items": [_news("What prompt caching changes for agents", "Latent Space", "TECH")]},
    ]
    picks = [_news("Designing CLIs that agents can drive", "Simon Willison", "AI",
                   why="Practical rules for tools that both people and agents use."),
             _news("Evaluating retrieval without labels", "Import AI", "RICERCA",
                   why="A cheap way to compare retrieval setups on your own data.")]
    sources = [{"name": name, "ok": True, "count": count, "error": None}
               for name, count in (("Hacker News", 30), ("Lobsters", 18), ("Hugging Face", 12), ("Latent Space", 4),
                                   ("Simon Willison", 6), ("Import AI", 2))]
    return {"edition": DAY, "updatedAt": NOW - 2 * 3600, "attemptedAt": NOW - 2 * 3600, "count": 72,
            "sources": sources, "headline": "Agents that test themselves, small models on laptops, cheaper caching",
            "topics": topics, "picks": picks, "error": None, "fetching": False}


def bar_menu(board, focus_state):
    icon = base64.b64encode((ROOT / "harlock-bar/icon/harlock.png").read_bytes()).decode("ascii")
    ctx = {"icon": icon, "cmd": "harlock-bar", "day_end": (18, 30)}
    return menu.build(focus_state, board, NOW, ctx)


def main():
    board = demo.model(now=NOW)
    focus_state = focus()
    print(json.dumps({"cc-panel": board, "focus-panel": focus_state, "news-panel": news(),
                      "harlock-bar": bar_menu(board, focus_state), "now": NOW}, ensure_ascii=False))


if __name__ == "__main__":
    main()

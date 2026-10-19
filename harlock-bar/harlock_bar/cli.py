"""Punto di ingresso del plugin xbar: senza argomenti stampa il menu, con argomenti esegue un'azione."""
import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from harlock_bar import menu

ROOT = Path(__file__).resolve().parent.parent
BOARD_MAX_AGE = 15 * 60  # oltre, i ticket si rileggono da Jira in background
KEY = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,6}$")
TITLE = "Arcadia"


def _home_path(var, default):
    return Path(os.environ.get(var) or Path.home() / default)


def state_path():
    return _home_path("HARLOCK_BAR_HOME", ".claude/harlock-bar") / "state.json"


def board_path():
    return _home_path("HARLOCK_BAR_BOARD", ".claude/cc-panel/board.json")


def focus_cli():
    return str(_home_path("HARLOCK_FOCUS_CLI", ".local/bin/focus-panel"))


def cc_cli():
    return str(_home_path("HARLOCK_CC_CLI", ".local/bin/cc-panel"))


# ------------------------------------------------------------------ processi e dialoghi

def run(argv, timeout=60):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, "", str(error)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def spawn(argv):
    """Avvia un processo staccato dal plugin: xbar non lo aspetta."""
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def _osascript(lines, *args):
    script = ["-e", "on run argv"] + [part for code in lines for part in ("-e", code)] + ["-e", "end run"]
    return run(["osascript"] + script + list(args), timeout=600)


def notify(text, sound=None):
    lines = ["display notification (item 1 of argv) with title (item 2 of argv)"
             + (" sound name (item 3 of argv)" if sound else "")]
    _osascript(lines, text, TITLE, *([sound] if sound else []))


def ask(prompt, default=""):
    """Chiede un testo con un dialogo; None se annullato."""
    code, out, _ = _osascript(["activate",
                               "text returned of (display dialog (item 1 of argv) default answer (item 2 of argv) "
                               "with title (item 3 of argv))"], prompt, default, TITLE)
    return out if code == 0 else None


# ------------------------------------------------------------------ stato locale

def load_state():
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def alert_box(focus):
    """Notifica una volta 5 minuti prima della fine del box e una volta alla fine."""
    box = (focus or {}).get("box")
    if not box or box["phase"] == "run":
        return
    state = load_state()
    key = "ended" if box["phase"] == "over" else "warned"
    if state.get(key) == box["start"]:
        return
    if box["phase"] == "over":
        notify("Tempo scaduto: %s" % box["text"], sound="Glass")
    else:
        notify("Ultimi 5 minuti: %s" % box["text"])
    state[key] = box["start"]
    save_state(state)


def refresh_board(now):
    state = load_state()
    if now - state.get("boardRefresh", 0) < BOARD_MAX_AGE:
        return False
    spawn([cc_cli(), "board", "--json"])
    state["boardRefresh"] = now
    save_state(state)
    return True


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_board(now):
    """Board di cc-panel; se è illeggibile (cc-panel la sta riscrivendo) usa l'ultima copia buona."""
    copy = state_path().with_name("board.json")
    board = _read_json(board_path())
    if board is not None:
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(json.dumps(board), encoding="utf-8")
    else:
        board = _read_json(copy)
    if board is None or now - board.get("updatedAt", 0) > BOARD_MAX_AGE:
        refresh_board(now)
    return board


def load_focus():
    code, out, _ = run([focus_cli(), "show"], timeout=20)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


# ------------------------------------------------------------------ menu e azioni

def _day_end():
    hour, _, minute = os.environ.get("HARLOCK_DAY_END", "18:30").partition(":")
    return int(hour), int(minute or 0)


def show():
    now = time.time()
    focus = load_focus()
    alert_box(focus)
    ctx = {"icon": base64.b64encode((ROOT / "icon/harlock.png").read_bytes()).decode("ascii"),
           "cmd": str(ROOT / "bin/harlock-bar"), "day_end": _day_end()}
    print("\n".join(menu.build(focus, load_board(now), now, ctx)))
    return 0


def _report(code, out, err):
    message = (out if code == 0 else err or out or "Errore").splitlines()
    notify(message[-1] if message else "Fatto")
    return 0 if code == 0 else 1


def add(when):
    text = ask("Main task per %s: verbo + oggetto" % when)
    if not text or not text.strip():
        return 0
    minutes = ask("Durata stimata in minuti", "30")
    if minutes is None:
        return 0
    if not minutes.strip().isdigit():
        notify("Durata non valida: %s" % minutes)
        return 1
    return _report(*run([focus_cli(), "add"] + text.split() + ["-m", minutes.strip(), "--when", when]))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return show()
    command, args = argv[0], argv[1:]
    if command == "focus":
        return _report(*run([focus_cli()] + args))
    if command == "add":
        return add(args[0] if args else "oggi")
    if command == "start":
        if not args or not KEY.match(args[0]):
            notify("Chiave ticket non valida")
            return 1
        spawn([cc_cli(), "start", args[0], "--auto"])
        notify("Riprendo %s…" % args[0])
        return 0
    if command == "board":
        save_state(dict(load_state(), boardRefresh=0))
        refresh_board(time.time())
        notify("Rileggo i ticket da Jira…")
        return 0
    print("Comando sconosciuto: %s" % command, file=sys.stderr)
    return 2

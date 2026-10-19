"""Apertura di una nuova finestra di Terminal.app con un comando."""
import shlex
import subprocess
from pathlib import Path

APPLICATIONS = Path("/Applications")
LAUNCH_TIMEOUT_SECONDS = 30


def new_session_command(cwd, name, brief_file):
    return 'cd %s && claude --ide --name %s "$(cat %s)"' % (
        shlex.quote(str(cwd)), shlex.quote(name), shlex.quote(str(brief_file)))


def resume_command(cwd, session_id):
    return "cd %s && claude --ide --resume %s" % (shlex.quote(str(cwd)), shlex.quote(session_id))


def open_folder_command(folder):
    return "cd %s" % shlex.quote(str(folder))


def preferred_app(applications=APPLICATIONS):
    """Ghostty se installato, altrimenti Terminal.app."""
    return "Ghostty" if (applications / "Ghostty.app").is_dir() else "Terminal"


def _applescript_string(text):
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')


def script(command, app):
    """AppleScript che apre una nuova finestra di `app` ed esegue `command` nella shell dell'utente."""
    if app == "Ghostty":
        # Il comando va come input iniziale: gira nella shell di login e la finestra resta aperta dopo.
        return ('tell application "Ghostty"\n'
                "  set cfg to new surface configuration\n"
                "  set initial input of cfg to %s & linefeed\n"
                "  new window with configuration cfg\n"
                "  activate\n"
                "end tell" % _applescript_string(command))
    return 'tell application "Terminal"\n  do script %s\n  activate\nend tell' % _applescript_string(command)


class LaunchError(Exception):
    def __init__(self, app, detail=""):
        super().__init__(
            "Non riesco ad aprire %s%s. Consenti il controllo di %s in Impostazioni di Sistema → "
            "Privacy e sicurezza → Automazione (per l'app da cui hai lanciato cc-panel)." % (
                app, ": %s" % detail if detail else "", app))


def launch(command):
    app = preferred_app()
    try:
        subprocess.run(["osascript", "-e", script(command, app)], check=True, capture_output=True, text=True,
                       timeout=LAUNCH_TIMEOUT_SECONDS)
    except subprocess.CalledProcessError as error:
        raise LaunchError(app, (error.stderr or "").strip()) from None
    except subprocess.TimeoutExpired:
        raise LaunchError(app, "nessuna risposta (permesso in attesa?)") from None

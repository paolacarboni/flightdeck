import subprocess
import tempfile
import unittest
from pathlib import Path

from cc_panel import terminal


class TerminalScriptTest(unittest.TestCase):
    def test_command_quotes_name_and_reads_brief(self):
        cmd = terminal.new_session_command(Path("/a b"), "OPS-1 l'utente \"vede\"", Path("/x/OPS-1.md"))
        self.assertEqual(cmd, "cd '/a b' && claude --ide --name 'OPS-1 l'\"'\"'utente \"vede\"' \"$(cat /x/OPS-1.md)\"")

    def test_resume_command(self):
        self.assertEqual(terminal.resume_command(Path("/r"), "abc-1"), "cd /r && claude --ide --resume abc-1")

    def compiles(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(["osacompile", "-o", str(Path(tmp) / "t.scpt"), "-e", source],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def special_command(self):
        return terminal.new_session_command(Path("/a b"), "OPS-1 l'utente \"vede\" \\ $HOME", Path("/x/OPS-1.md"))

    def test_ghostty_script_sends_command_as_initial_input(self):
        source = terminal.script(self.special_command(), "Ghostty")
        self.assertIn('tell application "Ghostty"', source)
        self.assertIn("initial input", source)
        self.compiles(source)

    def test_terminal_app_script_still_available(self):
        source = terminal.script(self.special_command(), "Terminal")
        self.assertIn('tell application "Terminal"', source)
        self.compiles(source)

    def test_ghostty_is_preferred_when_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Ghostty.app"
            app.mkdir()
            self.assertEqual(terminal.preferred_app(applications=Path(tmp)), "Ghostty")
            app.rmdir()
            self.assertEqual(terminal.preferred_app(applications=Path(tmp)), "Terminal")

    def test_open_folder_command(self):
        self.assertEqual(terminal.open_folder_command(Path("/a b")), "cd '/a b'")


class LaunchTest(unittest.TestCase):
    def test_osascript_failure_becomes_launch_error(self):
        from unittest import mock
        failure = subprocess.CalledProcessError(1, "osascript", stderr="Not authorized to send Apple events")
        with mock.patch("subprocess.run", side_effect=failure):
            with self.assertRaises(terminal.LaunchError) as ctx:
                terminal.launch("echo")
        self.assertIn("Automazione", str(ctx.exception))


class ForkCommandTest(unittest.TestCase):
    def test_fork_resumes_session_in_new_fork_with_quoted_prompt(self):
        cmd = terminal.fork_command(Path("/a b"), "abc-1", "Spiegami «cache-aside», non l'altro")
        self.assertEqual(cmd, "cd '/a b' && claude --resume abc-1 --fork-session "
                              "'Spiegami «cache-aside», non l'\"'\"'altro'")

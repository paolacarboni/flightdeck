import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

# Venerdì 17 ottobre 2026, ore 9: mattina, prima del mezzogiorno del frog.
NOW = datetime(2026, 10, 17, 9, 0).timestamp()


class TempHomeCase(unittest.TestCase):
    """Isola la home in una directory temporanea tramite FOCUS_PANEL_HOME."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self._old = os.environ.get("FOCUS_PANEL_HOME")
        os.environ["FOCUS_PANEL_HOME"] = str(self.home)
        # Nessun test deve avviare la vera lettura di Jira in background.
        spawn = mock.patch("focus_panel.deadlines._spawn_sync")
        self.spawned = spawn.start()
        self.addCleanup(spawn.stop)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("FOCUS_PANEL_HOME", None)
        else:
            os.environ["FOCUS_PANEL_HOME"] = self._old
        self._tmp.cleanup()

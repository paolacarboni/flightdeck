import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FIXTURES = Path(__file__).parent / "fixtures"


class TempHomeCase(unittest.TestCase):
    """Isola la home in una directory temporanea tramite NEWS_PANEL_HOME."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self._old = os.environ.get("NEWS_PANEL_HOME")
        os.environ["NEWS_PANEL_HOME"] = str(self.home)
        # Nessun test deve avviare la vera raccolta in background (rete e chiamate a Claude).
        spawn = mock.patch("news_panel.edition._spawn_fetch")
        self.spawned = spawn.start()
        self.addCleanup(spawn.stop)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("NEWS_PANEL_HOME", None)
        else:
            os.environ["NEWS_PANEL_HOME"] = self._old
        self._tmp.cleanup()

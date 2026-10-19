import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cc_panel.llm import LLMError


class TempHomeCase(unittest.TestCase):
    """Isola home e vault in directory temporanee tramite le env di cc-panel."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.home = root / "home"
        self.vault = root / "vault"
        self.home.mkdir()
        self.vault.mkdir()
        env = {"CC_PANEL_HOME": str(self.home), "CC_PANEL_NOTES_DIR": str(self.vault / "Jira"),
               "CC_PANEL_JIRA_URL": "https://example.atlassian.net", "CC_PANEL_JIRA_EMAIL": "me@example.com",
               "CC_PANEL_DEFAULT_PROJECT": "", "CC_PANEL_PROJECTS_DIR": ""}
        self._env = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        # Nessun test deve avviare la vera valutazione in background (chiamate reali a Claude).
        spawn = mock.patch("cc_panel.board._spawn_digest")
        self.spawned_digest = spawn.start()
        self.addCleanup(spawn.stop)
        index = mock.patch("cc_panel.repoindex.spawn_build")
        self.spawned_index = index.start()
        self.addCleanup(index.stop)
        # Né Claude reale: ogni chiamata non simulata dal test fallisce come se Claude non rispondesse.
        claude = mock.patch("cc_panel.llm.structured", side_effect=LLMError("Claude non disponibile nei test"))
        claude.start()
        self.addCleanup(claude.stop)

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

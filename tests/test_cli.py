import io
import tempfile
import unittest
from unittest import mock

from cc_panel import cli


class OpenCommandTest(unittest.TestCase):
    def test_open_launches_terminal_in_folder(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("cc_panel.terminal.launch") as launch:
            self.assertEqual(cli.main(["open", tmp]), 0)
        launch.assert_called_once_with("cd %s" % tmp)

    def test_open_rejects_missing_folder(self):
        with mock.patch("cc_panel.terminal.launch") as launch, mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(cli.main(["open", "/non/esiste"]), 1)
        launch.assert_not_called()


class DigestCommandTest(unittest.TestCase):
    def test_digest_reports_count(self):
        with mock.patch("cc_panel.digest.run", return_value=4), mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(cli.main(["digest"]), 0)
        self.assertIn("4", out.getvalue())

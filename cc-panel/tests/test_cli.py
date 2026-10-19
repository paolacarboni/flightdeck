import io
import tempfile
import unittest
from unittest import mock

from cc_panel import cli, repoindex


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


class IndexCommandTest(unittest.TestCase):
    def run_cli(self, argv):
        with mock.patch("sys.stdout", io.StringIO()) as out, mock.patch("sys.stderr", io.StringIO()) as err:
            code = cli.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_index_reports_counts_and_missing_semantic_setup(self):
        meta = {"candidates": [1, 2], "chunks": [1, 2, 3]}
        with mock.patch("cc_panel.repoindex.build", return_value=meta), \
                mock.patch("cc_panel.semantic.python", return_value=None):
            code, output = self.run_cli(["index"])
        self.assertEqual(code, 0)
        self.assertIn("2 repo, 3 frammenti", output)
        self.assertIn("cc-panel semantic-setup", output)

    def test_index_already_running(self):
        with mock.patch("cc_panel.repoindex.build", return_value=None):
            code, output = self.run_cli(["index"])
        self.assertEqual(code, 0)
        self.assertIn("già in corso", output)

    def test_index_vectors_failure_is_reported(self):
        with mock.patch("cc_panel.repoindex.build", side_effect=repoindex.VectorsError("IndexMismatch")):
            code, output = self.run_cli(["index"])
        self.assertEqual(code, 1)
        self.assertIn("IndexMismatch", output)

    def test_semantic_setup_passes_the_source_folder(self):
        with mock.patch("cc_panel.semantic.setup", return_value=0) as setup:
            code, _ = self.run_cli(["semantic-setup", "--from", "/scaricati"])
        self.assertEqual(code, 0)
        self.assertEqual(setup.call_args.kwargs["source"], "/scaricati")

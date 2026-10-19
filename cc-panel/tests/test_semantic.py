import hashlib
import io
import json
import subprocess
from unittest import mock

from cc_panel import semantic
from tests.helpers import TempHomeCase

CONTENT = {"model_quantized.onnx": b"onnx finto", "tokenizer.json": b'{"tokenizer": "finto"}'}
FILES = {name: ("remoto/%s" % name, hashlib.sha256(data).hexdigest()) for name, data in CONTENT.items()}


class SemanticTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.source = self.home / "scaricati"
        self.source.mkdir()
        for name, data in CONTENT.items():
            (self.source / name).write_bytes(data)
        self.commands = []

    def fake_run(self, command, **kwargs):
        self.commands.append([str(part) for part in command])
        if "venv" in command:
            python = semantic.venv_dir() / "bin/python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("")
        return subprocess.CompletedProcess(command, 0, "", "")

    def setup(self, **kwargs):
        out = io.StringIO()
        code = semantic.setup(source=str(self.source), run=self.fake_run, out=out, files=FILES, **kwargs)
        self.out = out.getvalue()
        return code

    def test_python_is_none_until_venv_and_verified_model_exist(self):
        self.assertIsNone(semantic.python(files=FILES))
        self.assertEqual(self.setup(), 0)
        self.assertEqual(semantic.python(files=FILES), semantic.venv_dir() / "bin/python")
        for name, data in CONTENT.items():
            self.assertEqual((semantic.model_dir() / name).read_bytes(), data)

    def test_changed_model_file_is_not_trusted(self):
        self.setup()
        (semantic.model_dir() / "tokenizer.json").write_bytes(b"manomesso, lunghezza diversa")
        self.assertIsNone(semantic.python(files=FILES))

    def test_wrong_hash_is_refused_and_nothing_is_installed(self):
        (self.source / "tokenizer.json").write_bytes(b"altro")
        self.assertEqual(self.setup(), 1)
        self.assertIn("sha256", self.out)
        self.assertFalse((semantic.model_dir() / "tokenizer.json").exists())
        self.assertIsNone(semantic.python(files=FILES))

    def test_pinned_requirements_with_uv_when_available(self):
        with mock.patch("shutil.which", return_value="/opt/uv"):
            self.setup()
        self.assertEqual(self.commands[0][:2], ["/opt/uv", "venv"])
        install = self.commands[1]
        self.assertEqual(install[:3], ["/opt/uv", "pip", "install"])
        for requirement in semantic.REQUIREMENTS:
            self.assertIn(requirement, install)

    def test_setup_can_be_repeated_on_an_existing_venv(self):
        python = semantic.venv_dir() / "bin/python"
        python.parent.mkdir(parents=True)
        python.write_text("")
        with mock.patch("shutil.which", return_value="/opt/uv"):
            self.assertEqual(self.setup(), 0)
        self.assertEqual([c[:3] for c in self.commands], [["/opt/uv", "pip", "install"]])

    def test_pip_fallback_without_uv(self):
        with mock.patch("shutil.which", return_value=None):
            self.setup()
        self.assertEqual(self.commands[0][1:3], ["-m", "venv"])
        self.assertEqual(self.commands[1][1:4], ["-m", "pip", "install"])

    def test_download_uses_curl_on_pinned_revision(self):
        def fake_run(command, **kwargs):
            self.commands.append([str(part) for part in command])
            if command[0] == "curl":
                target = command[command.index("-o") + 1]
                name = next(n for n in CONTENT if command[-1].endswith(n))
                with open(target, "wb") as handle:
                    handle.write(CONTENT[name])
            return subprocess.CompletedProcess(command, 0, "", "")
        with mock.patch("shutil.which", return_value=None):
            code = semantic.setup(run=fake_run, out=io.StringIO(), files=FILES)
        self.assertEqual(code, 0)
        urls = [c[-1] for c in self.commands if c[0] == "curl"]
        self.assertEqual(sorted(urls), sorted("https://huggingface.co/%s/resolve/%s/remoto/%s"
                                              % (semantic.MODEL_REPO, semantic.MODEL_REVISION, n) for n in CONTENT))

    def test_failed_install_stops_setup(self):
        def failing(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "", "rete assente")
        code = semantic.setup(source=str(self.source), run=failing, out=io.StringIO(), files=FILES)
        self.assertEqual(code, 1)
        self.assertIsNone(semantic.python(files=FILES))

    def test_marker_records_the_model_id(self):
        self.setup()
        marker = json.loads((semantic.model_dir() / "verified.json").read_text())
        self.assertEqual(marker["model"], semantic.MODEL_ID)

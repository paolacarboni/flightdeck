import json
import subprocess
from unittest import mock

from cc_panel import llm
from tests.helpers import TempHomeCase

# Catturata all'import: in setUp gli helper sostituiscono llm.structured con un mock.
STRUCTURED = llm.structured
SCHEMA = {"type": "object"}


def completed(stdout, returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class LLMTest(TempHomeCase):
    def call(self, result=None, error=None):
        with mock.patch("subprocess.run", return_value=result, side_effect=error) as run:
            try:
                return STRUCTURED("domanda", SCHEMA, 42)
            finally:
                self.run_call = run.call_args

    def test_returns_structured_output(self):
        payload = {"is_error": False, "structured_output": {"index": 2}}
        self.assertEqual(self.call(completed(json.dumps(payload))), {"index": 2})
        command = self.run_call.args[0]
        self.assertEqual(command[command.index("--json-schema") + 1], json.dumps(SCHEMA))
        self.assertIn("haiku", command)
        self.assertEqual(self.run_call.kwargs["input"], "domanda")
        self.assertEqual(self.run_call.kwargs["timeout"], 42)

    def test_failures_raise_llm_error(self):
        cases = [
            completed(json.dumps({"structured_output": {"a": 1}}), returncode=1),
            completed(json.dumps({"is_error": True, "result": "limite raggiunto"})),
            completed(json.dumps({"is_error": False, "structured_output": None})),
            completed("non json"),
        ]
        for result in cases:
            with self.subTest(stdout=result.stdout), self.assertRaises(llm.LLMError):
                self.call(result)
        for error in (subprocess.TimeoutExpired("claude", 42), OSError("claude assente")):
            with self.subTest(error=error), self.assertRaises(llm.LLMError):
                self.call(error=error)

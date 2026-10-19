"""Chiamata a Claude Haiku senza tool e senza sessione salvata, con risposta vincolata da uno schema JSON."""
import json
import shutil
import subprocess
from pathlib import Path

from cc_panel import paths


class LLMError(Exception):
    pass


def structured(prompt, schema, timeout):
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    command = [claude, "-p", "--model", "haiku", "--no-session-persistence", "--tools", "",
               "--output-format", "json", "--json-schema", json.dumps(schema)]
    try:
        result = subprocess.run(command, input=prompt, capture_output=True, text=True,
                                timeout=timeout, cwd=str(paths.home()))
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as error:
        raise LLMError(str(error)) from None
    if result.returncode != 0 or payload.get("is_error") or not isinstance(payload.get("structured_output"), dict):
        raise LLMError((payload.get("result") or result.stderr or "risposta senza dati")[:200])
    return payload["structured_output"]

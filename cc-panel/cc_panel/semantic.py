"""Ricerca semantica della cartella: venv dedicato e modello verificato.

numpy, onnxruntime e tokenizers stanno in ~/.cc-panel/venv, non nel python di sistema: cc-panel resta
stdlib e chiama `python -m cc_panel.embed` del venv. Il modello è fissato per revisione e sha256;
`cc-panel semantic-setup` scarica (o copia da --from), verifica e solo dopo installa.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cc_panel import paths

MODEL_REPO = "Xenova/multilingual-e5-small"
MODEL_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
MODEL_ID = "%s@%s" % (MODEL_REPO, MODEL_REVISION)
MODEL_FILES = {
    "model_quantized.onnx": ("onnx/model_quantized.onnx",
                             "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193"),
    "tokenizer.json": ("tokenizer.json", "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
}
REQUIREMENTS = ("numpy==2.0.2", "onnxruntime==1.19.2", "tokenizers==0.22.2")
INDEX_TIMEOUT_SECONDS = 15 * 60
STEP_TIMEOUT_SECONDS = 15 * 60


class SetupError(Exception):
    pass


def base_dir():
    return paths.home() / ".cc-panel"


def venv_dir():
    return base_dir() / "venv"


def model_dir():
    return base_dir() / "models/multilingual-e5-small"


def package_root():
    return Path(__file__).resolve().parent.parent


def _marker():
    return model_dir() / "verified.json"


def python(files=MODEL_FILES):
    """Python del venv se venv e modello verificato ci sono, altrimenti None.

    Confronta dimensione e mtime registrati dal setup: ricalcolare lo sha256 di 118 MB a ogni proposta
    costerebbe più del budget.
    """
    venv_python = venv_dir() / "bin/python"
    if not venv_python.exists():
        return None
    try:
        recorded = json.loads(_marker().read_text(encoding="utf-8")).get("files", {})
    except (OSError, ValueError, AttributeError):
        return None
    for name, (_, digest) in files.items():
        entry = recorded.get(name) or {}
        try:
            stat = (model_dir() / name).stat()
        except OSError:
            return None
        if entry.get("sha256") != digest or entry.get("size") != stat.st_size or entry.get("mtime") != stat.st_mtime:
            return None
    return venv_python


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(result, what):
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-300:]
        raise SetupError("%s non riuscito: %s" % (what, detail or "codice %d" % result.returncode))


def _fetch(name, remote, source, run, target):
    if source:
        shutil.copyfile(str(Path(source).expanduser() / name), str(target))
        return
    url = "https://huggingface.co/%s/resolve/%s/%s" % (MODEL_REPO, MODEL_REVISION, remote)
    # Il proxy viene dall'ambiente; --proxy-negotiate serve solo se il proxy chiede Kerberos.
    _check(run(["curl", "-fsSL", "--retry", "2", "--connect-timeout", "20", "--proxy-negotiate", "-U", ":",
                "-o", str(target), url],
               capture_output=True, text=True, timeout=STEP_TIMEOUT_SECONDS), "download di %s" % name)


def _install(run):
    venv, uv = venv_dir(), shutil.which("uv")
    venv_python = venv / "bin/python"
    if uv:
        steps = [[uv, "venv", "--python", sys.executable, str(venv)],
                 [uv, "pip", "install", "--python", str(venv_python), "--only-binary", ":all:"] + list(REQUIREMENTS)]
    else:
        steps = [[sys.executable, "-m", "venv", str(venv)],
                 [str(venv_python), "-m", "pip", "install", "--only-binary=:all:"] + list(REQUIREMENTS)]
    work = list(zip(steps, ("creazione del venv", "installazione di %s" % ", ".join(REQUIREMENTS))))
    if venv_python.exists():  # setup ripetuto: il venv c'è già, si aggiornano solo le dipendenze
        work = work[1:]
    for step, what in work:
        _check(run(step, capture_output=True, text=True, timeout=STEP_TIMEOUT_SECONDS), what)


def setup(source=None, run=subprocess.run, out=sys.stdout, files=MODEL_FILES):
    """Modello verificato (scaricato, o copiato dalla cartella `source`) e venv con le versioni fissate; 0 se pronto."""
    staging = base_dir() / "download"
    try:
        shutil.rmtree(str(staging), ignore_errors=True)
        staging.mkdir(parents=True)
        for name, (remote, digest) in files.items():
            print("Modello: %s…" % name, file=out)
            _fetch(name, remote, source, run, staging / name)
            found = _sha256(staging / name)
            if found != digest:
                raise SetupError("sha256 di %s non corrisponde: atteso %s, trovato %s" % (name, digest, found))
        print("Venv: %s" % venv_dir(), file=out)
        _install(run)
        target = model_dir()
        target.mkdir(parents=True, exist_ok=True)
        recorded = {}
        for name, (_, digest) in files.items():
            os.replace(str(staging / name), str(target / name))
            stat = (target / name).stat()
            recorded[name] = {"sha256": digest, "size": stat.st_size, "mtime": stat.st_mtime}
        _marker().write_text(json.dumps({"model": MODEL_ID, "files": recorded}, indent=2), encoding="utf-8")
    except (SetupError, OSError, subprocess.TimeoutExpired) as error:
        print("Ricerca semantica non pronta: %s" % error, file=out)
        return 1
    finally:
        shutil.rmtree(str(staging), ignore_errors=True)
    print("Ricerca semantica pronta: ora `cc-panel index` costruisce l'indice.", file=out)
    return 0

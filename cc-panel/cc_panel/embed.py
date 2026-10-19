"""Lato denso della ricerca della cartella, eseguito con il python del venv (numpy, onnxruntime, tokenizers).

`python -m cc_panel.embed index <cartella>`: vettori dei frammenti di meta.json, ricalcolando solo i testi
nuovi (cache per hash del testo). `python -m cc_panel.embed query <cartella>`: testo del ticket da stdin,
su stdout `{"groups": [[candidato, punteggio, frammento migliore], ...]}` dal più simile.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

from cc_panel import semantic

MAX_TOKENS = 512
BATCH = 32
THREADS = 4


class IndexMismatch(Exception):
    pass


def pool(hidden, mask):
    """Media dei vettori dei soli token reali (mean pooling), normalizzata."""
    weights = mask[..., None].astype(hidden.dtype)
    summed = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
    return summed / np.clip(np.linalg.norm(summed, axis=1, keepdims=True), 1e-12, None)


class Model:
    """multilingual-e5-small: prefissi «query: » e «passage: », mean pooling, vettori normalizzati."""

    def __init__(self, folder=None):
        import onnxruntime
        from tokenizers import Tokenizer
        folder = folder or semantic.model_dir()
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = THREADS
        self.session = onnxruntime.InferenceSession(str(folder / "model_quantized.onnx"), options,
                                                    providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        self.tokenizer.enable_padding()

    def encode(self, texts, kind):
        # Lotti di testi di lunghezza simile: meno padding, indicizzazione più rapida.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        result = [None] * len(texts)
        for start in range(0, len(order), BATCH):
            batch = order[start:start + BATCH]
            encoded = self.tokenizer.encode_batch(["%s: %s" % (kind, texts[i]) for i in batch])
            ids = np.array([e.ids for e in encoded], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            for i, vector in zip(batch, pool(self.session.run(None, feed)[0], mask)):
                result[i] = vector
        return np.array(result, dtype=np.float32)


def group_scores(vectors, groups, vector):
    """Per candidato il frammento più simile: [[candidato, punteggio, frammento]] dal punteggio più alto."""
    best = {}
    for index, (group, score) in enumerate(zip(groups, (vectors @ vector).tolist())):
        if group not in best or score > best[group][0]:
            best[group] = (score, index)
    return sorted(([group, score, index] for group, (score, index) in best.items()), key=lambda row: -row[1])


def _key(text):
    return hashlib.sha1(("%s\n%s" % (semantic.MODEL_ID, text)).encode("utf-8")).hexdigest()


def _meta(folder):
    return json.loads((folder / "meta.json").read_text(encoding="utf-8"))


def _replace(target, write):
    temporary = target.with_name("tmp-" + target.name)
    write(temporary)
    os.replace(str(temporary), str(target))


def build_vectors(folder, model):
    meta = _meta(folder)
    texts = [chunk["text"] for chunk in meta["chunks"]]
    cache = {}
    try:
        with np.load(str(folder / "cache.npz")) as saved:
            cache = dict(zip(saved["keys"].tolist(), saved["vectors"]))
    except (OSError, ValueError, KeyError):
        pass
    keys = [_key(text) for text in texts]
    missing = {key: text for key, text in zip(keys, texts) if key not in cache}
    if missing:
        cache.update(zip(missing, model.encode(list(missing.values()), "passage")))
    vectors = np.array([cache[key] for key in keys], dtype=np.float32)
    _replace(folder / "vectors.npy", lambda path: np.save(str(path), vectors))
    kept = sorted(set(keys))
    _replace(folder / "cache.npz", lambda path: np.savez(str(path), keys=np.array(kept),
                                                         vectors=np.array([cache[k] for k in kept], dtype=np.float32)))
    info = {"builtAt": meta["builtAt"], "model": semantic.MODEL_ID, "rows": len(keys)}
    _replace(folder / "vectors.json", lambda path: path.write_text(json.dumps(info), encoding="utf-8"))


def query(folder, text, model):
    meta = _meta(folder)
    info = json.loads((folder / "vectors.json").read_text(encoding="utf-8"))
    vectors = np.load(str(folder / "vectors.npy"))
    rows = len(meta["chunks"])
    if (info.get("builtAt"), info.get("model"), info.get("rows"), vectors.shape[0]) != \
            (meta.get("builtAt"), semantic.MODEL_ID, rows, rows):
        raise IndexMismatch("vettori non allineati all'indice: ricostruiscilo con `cc-panel index`")
    return group_scores(vectors, [chunk["group"] for chunk in meta["chunks"]], model.encode([text], "query")[0])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("index", "query"):
        print("uso: python -m cc_panel.embed index|query <cartella>", file=sys.stderr)
        return 2
    folder = Path(argv[1])
    try:
        model = Model()
        if argv[0] == "index":
            build_vectors(folder, model)
        else:
            print(json.dumps({"groups": query(folder, sys.stdin.read(), model)}))
    except Exception as error:  # noqa: BLE001 — processo figlio: il chiamante legge solo codice d'uscita e messaggio
        print("%s: %s" % (type(error).__name__, error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

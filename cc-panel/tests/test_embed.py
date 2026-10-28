import json
import unittest

from tests.helpers import TempHomeCase

try:
    import numpy as np
except ImportError:  # numpy c'è di sicuro solo nel venv della ricerca semantica
    np = None
if np is not None:
    from cc_panel import embed, repoindex


class FakeModel:
    """Vettori deterministici: una dimensione per parola nota; conta i testi codificati."""
    WORDS = ["fatture", "telemetria", "tag", "atlas"]

    def __init__(self):
        self.encoded = []

    def encode(self, texts, kind):
        self.encoded.extend(texts)
        rows = [[float(word in text.lower()) for word in self.WORDS] + [0.1] for text in texts]
        matrix = np.array(rows, dtype=np.float32)
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


@unittest.skipIf(np is None, "numpy non disponibile")
class EmbedTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.folder = self.home / "index"
        self.folder.mkdir()
        self.chunks = [{"group": 0, "kind": "nome", "label": "nome", "text": "app fatture"},
                       {"group": 0, "kind": "readme", "label": "README: App", "text": "calcolo fatture e tag"},
                       {"group": 1, "kind": "nome", "label": "nome", "text": "orion telemetria"},
                       {"group": 2, "kind": "nome", "label": "nome", "text": "atlas"}]
        self.write_meta(1000.0)

    def write_meta(self, built_at):
        """Meta della build in corso, come lo scrive repoindex.build prima di calcolare i vettori."""
        (self.folder / repoindex.NEXT_META).write_text(json.dumps({"version": 1, "builtAt": built_at,
                                                                   "candidates": [], "chunks": self.chunks}))

    def build_and_publish(self, model):
        embed.build_vectors(self.folder, model)
        repoindex._publish(self.folder)

    def test_pool_averages_only_real_tokens_and_normalizes(self):
        hidden = np.array([[[1.0, 0.0], [3.0, 0.0], [100.0, 100.0]]])
        mask = np.array([[1, 1, 0]])
        np.testing.assert_allclose(embed.pool(hidden, mask), [[1.0, 0.0]])

    def test_group_scores_keep_best_chunk_per_group_sorted(self):
        vectors = np.array([[1.0, 0.0], [0.6, 0.8], [0.0, 1.0]], dtype=np.float32)
        scores = embed.group_scores(vectors, [0, 0, 1], np.array([0.6, 0.8], dtype=np.float32))
        self.assertEqual([row[0] for row in scores], [0, 1])
        self.assertAlmostEqual(scores[0][1], 1.0, places=5)
        self.assertEqual(scores[0][2], 1)
        self.assertAlmostEqual(scores[1][1], 0.8, places=5)

    def test_index_writes_aligned_vectors_and_reuses_cache(self):
        model = FakeModel()
        embed.build_vectors(self.folder, model)
        self.assertEqual(np.load(str(self.folder / repoindex.NEXT_VECTORS)).shape[0], len(self.chunks))
        self.assertFalse((self.folder / repoindex.VECTORS).exists())
        self.chunks[3]["text"] = "atlas telemetria"
        self.write_meta(2000.0)
        model.encoded = []
        embed.build_vectors(self.folder, model)
        self.assertEqual(model.encoded, ["atlas telemetria"])
        info = json.loads((self.folder / repoindex.NEXT_VECTORS_INFO).read_text())
        self.assertEqual(info, {"builtAt": 2000.0, "model": embed.semantic.MODEL_ID, "rows": 4})

    def test_corrupted_cache_is_rebuilt(self):
        (self.folder / repoindex.CACHE).write_bytes(b"PK\x03\x04 zip troncato")
        model = FakeModel()
        embed.build_vectors(self.folder, model)
        self.assertEqual(len(model.encoded), len(self.chunks))

    def test_query_ranks_groups(self):
        model = FakeModel()
        self.build_and_publish(model)
        scores = embed.query(self.folder, "telemetria della repository", model)
        self.assertEqual(scores[0][0], 1)
        self.assertEqual(scores[0][2], 2)
        self.assertEqual(len(scores), 3)

    def test_query_refuses_vectors_of_another_index(self):
        self.build_and_publish(FakeModel())
        self.write_meta(3000.0)
        repoindex._publish(self.folder)
        with self.assertRaises(embed.IndexMismatch):
            embed.query(self.folder, "fatture", FakeModel())

    def test_query_without_vectors_is_a_mismatch_not_a_crash(self):
        repoindex._publish(self.folder)
        with self.assertRaises(embed.IndexMismatch):
            embed.query(self.folder, "fatture", FakeModel())

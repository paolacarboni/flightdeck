import json
import subprocess
from unittest import mock

from cc_panel import placement, repoindex
from tests.helpers import TempHomeCase

ISSUE = {"key": "OPS-9", "summary": "FinOps e tagging della repository alpha-service", "type": "Task",
         "epic": "OPS-1", "epic_summary": "Dev Kit", "description": "Applicare i tag di costo alle risorse",
         "comments": [{"author": "Ada", "created": "2026-10-19", "body": "vedi   anche\nla pipeline"}], "url": "u"}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class RankTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.folders = {}
        names = ["alpha-service", "billing-engine", "cost-tagger", "docs-site", "atlas-bff"]
        candidates = []
        for name in names:
            folder = self.home / "Projects" / name
            folder.mkdir(parents=True)
            self.folders[name] = folder
            candidates.append({"group": "origin:" + name, "folder": str(folder), "folders": [str(folder)], "names": [name]})
        texts = {
            "alpha-service": ["alpha-service", "README alpha service per i pagamenti"],
            "billing-engine": ["billing-engine", "tagging finops dei costi e tag di costo delle risorse cloud"],
            "cost-tagger": ["cost-tagger", "tag di costo"],
            "docs-site": ["docs-site", "documentazione"],
            "atlas-bff": ["atlas-bff", "assistente atlas"],
        }
        self.chunks = []
        for group, name in enumerate(names):
            self.chunks.append({"group": group, "kind": "nome", "label": "nome", "text": texts[name][0]})
            self.chunks.append({"group": group, "kind": "readme", "label": "README: %s" % name, "text": texts[name][1]})
        self.write_meta(candidates)
        self.clock = Clock()
        self.warnings = []

    def write_meta(self, candidates, version=repoindex.VERSION, built_at=None):
        repoindex.index_dir().mkdir(parents=True, exist_ok=True)
        (repoindex.index_dir() / "meta.json").write_text(json.dumps({
            "version": version, "builtAt": built_at if built_at is not None else __import__("time").time(),
            "candidates": candidates, "chunks": self.chunks}))
        self.candidates = candidates

    def rank(self, dense=None, issue=ISSUE, budget=2.0):
        def no_dense(text, timeout):
            raise placement.DenseError("non installata")
        return placement.rank(issue, budget=budget, dense=dense or no_dense, clock=self.clock, warn=self.warnings.append)

    def names(self, results):
        return [folder.name for folder, _ in results]

    def test_fuse_is_reciprocal_rank_fusion_with_name_boost(self):
        # g1: 3º, 2º, citato → 1/63 + 1/62 + 1/61; g0: 2º, 1º → 1/62 + 1/61; g2: 1º → 1/61
        self.assertEqual(placement.fuse([[2, 0, 1], [0, 1]], {1}), [1, 0, 2])

    def test_bm25_prefers_rare_matching_terms_and_ignores_unrelated(self):
        scores = placement.bm25(["telemetria costi", "costi costi costi", "atlas"], "telemetria dei costi")
        self.assertGreater(scores[0], scores[1])
        self.assertEqual(scores[2], 0.0)

    def test_mentioned_name_is_normalized_and_long_enough(self):
        self.assertTrue(placement.mentioned({"names": ["acme-dev-kit"]}, "tagging della repository acme-devkit-telemetry"))
        self.assertFalse(placement.mentioned({"names": ["docs"]}, "aggiornare i docs"))
        self.assertFalse(placement.mentioned({"names": ["billing-engine"]}, "motore di fatturazione"))

    def test_query_text_uses_summary_epic_description_and_comments(self):
        text = placement.query_text(dict(ISSUE, description="x" * 5000))
        for part in ("FinOps e tagging", "Dev Kit", "Ada: vedi anche la pipeline"):
            self.assertIn(part, text)
        self.assertIn("x" * placement.DESCRIPTION_LIMIT, text)
        self.assertNotIn("x" * (placement.DESCRIPTION_LIMIT + 1), text)

    def test_hybrid_top3_with_evidence(self):
        def dense(text, timeout):
            self.timeout = timeout
            return {1: (0.9, 3), 2: (0.8, 5), 0: (0.7, 1), 3: (0.1, 6), 4: (0.05, 8)}
        results = self.rank(dense)
        self.assertEqual(self.names(results), ["alpha-service", "billing-engine", "cost-tagger"])
        self.assertEqual([evidence for _, evidence in results],
                         ["nome citato nel ticket", "README: billing-engine", "README: cost-tagger"])
        self.assertLessEqual(self.timeout, 2.0)
        self.assertEqual(self.warnings, [])

    def test_dense_timeout_is_the_remaining_budget(self):
        original = repoindex.load

        def slow_load():
            self.clock.now = 0.5
            return original()

        def dense(text, timeout):
            self.timeout = timeout
            return {}
        with mock.patch("cc_panel.repoindex.load", side_effect=slow_load):
            self.rank(dense)
        self.assertAlmostEqual(self.timeout, 2.0 - 0.5 - placement.FUSION_RESERVE_SECONDS)

    def test_mismatched_vectors_trigger_a_rebuild(self):
        def dense(text, timeout):
            raise placement.DenseError("IndexMismatch: vettori non allineati", rebuild=True)
        self.assertEqual(len(self.rank(dense)), 3)
        self.spawned_index.assert_called_once()
        self.assertIn("ricostruisco l'indice", self.warnings[0])

    def test_dense_scores_outside_the_index_are_discarded(self):
        for scores in ({99: (0.9, 0)}, {0: (0.9, 999)}, {0: (0.9, 3)}):
            with self.subTest(scores=scores):
                self.spawned_index.reset_mock()
                results = self.rank(lambda text, timeout, scores=scores: scores)
                self.assertTrue(all(not evidence.startswith("README") for _, evidence in results[1:]))
                self.spawned_index.assert_called_once()

    def test_dense_failure_gives_lexical_results_and_a_warning(self):
        results = self.rank()
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][0], self.folders["alpha-service"])
        self.assertTrue(results[1][1].startswith("parole in comune: "))
        self.assertEqual(self.warnings, ["ricerca semantica non disponibile (non installata): uso solo le parole del ticket"])

    def test_no_dense_call_when_the_budget_is_already_spent(self):
        calls = []

        def dense(text, timeout):
            calls.append(timeout)
            return {}

        original = repoindex.load

        def slow_load():
            self.clock.now = 1.95
            return original()
        with mock.patch("cc_panel.repoindex.load", side_effect=slow_load):
            results = self.rank(dense)
        self.assertEqual(calls, [])
        self.assertEqual(self.names(results)[0], "alpha-service")
        self.assertEqual(self.warnings, ["ricerca semantica saltata (tempo esaurito): uso solo le parole del ticket"])

    def test_missing_or_foreign_index_triggers_build_and_proposes_nothing(self):
        (repoindex.index_dir() / "meta.json").unlink()
        self.assertEqual(self.rank(), [])
        self.write_meta(self.candidates, version=repoindex.VERSION + 1)
        self.assertEqual(self.rank(), [])
        self.assertEqual(self.spawned_index.call_count, 2)

    def test_stale_index_is_used_and_rebuilt_in_background(self):
        self.write_meta(self.candidates, built_at=1.0)
        self.assertEqual(len(self.rank()), 3)
        self.spawned_index.assert_called_once()

    def dense_all(self, text, timeout):
        return {group: (1.0 - group / 10, group * 2) for group in range(len(self.candidates))}

    def test_title_only_ticket_gets_three_with_dense_and_only_matches_without(self):
        bare = dict(ISSUE, summary="Sistemare la documentazione", epic=None, epic_summary=None, description="", comments=[])
        self.assertEqual(len(self.rank(self.dense_all, issue=bare)), 3)
        self.assertEqual(self.names(self.rank(issue=bare)), ["docs-site"])

    def test_worktree_named_after_the_key_represents_the_group(self):
        worktree = self.home / "Projects/alpha-service-OPS-9"
        worktree.mkdir()
        self.candidates[0]["folders"].append(str(worktree))
        self.write_meta(self.candidates)
        self.assertEqual(self.rank()[0][0], worktree)

    def test_worktree_must_contain_the_whole_key(self):
        main = self.folders["alpha-service"]
        cases = [("alpha-ops-572-ci", "OPS-57", main), ("alpha-ops586", "OPS-586", "alpha-ops586"),
                 ("alpha-OPS-9", "OPS-9", "alpha-OPS-9"), ("alpha-OPS-90", "OPS-9", main), ("xai-9", "OPS-9", main)]
        for name, key, expected in cases:
            with self.subTest(name=name, key=key):
                worktree = self.home / "Projects" / name
                worktree.mkdir(exist_ok=True)
                candidate = dict(self.candidates[0], folders=[str(main), str(worktree)])
                found = placement._folder(candidate, key)
                self.assertEqual(found, worktree if isinstance(expected, str) else expected)

    def test_deleted_folders_are_skipped(self):
        self.folders["alpha-service"].rmdir()
        results = self.rank(self.dense_all)
        self.assertNotIn("alpha-service", self.names(results))
        self.assertEqual(len(results), 3)


class FakePopen:
    """Sostituto di subprocess.Popen: risponde a communicate come il figlio `embed query`."""

    def __init__(self, stdout="", stderr="", code=0, hang=False):
        self.stdout, self.stderr, self.code, self.hang = stdout, stderr, code, hang
        self.returncode, self.killed = None, False

    def __call__(self, command, **kwargs):
        self.command, self.kwargs = command, kwargs
        return self

    def communicate(self, input=None, timeout=None):
        self.input, self.timeout = input, timeout
        if self.hang:
            raise subprocess.TimeoutExpired("python", timeout)
        self.returncode = self.code
        return self.stdout, self.stderr

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True

    def wait(self):
        self.returncode = -9


class DenseProcessTest(TempHomeCase):
    def run_dense(self, popen, python="/venv/bin/python"):
        with mock.patch("cc_panel.semantic.python", return_value=python), mock.patch("subprocess.Popen", popen):
            return placement._dense("testo", 1.5)

    def test_scores_parsed_from_the_child_process(self):
        popen = FakePopen(json.dumps({"groups": [[2, 0.8, 7], [0, 0.5, 1]]}))
        self.assertEqual(self.run_dense(popen), {2: (0.8, 7), 0: (0.5, 1)})
        self.assertEqual((popen.input, popen.timeout), ("testo", 1.5))
        self.assertEqual(popen.command[:4], ["/venv/bin/python", "-m", "cc_panel.embed", "query"])
        self.assertFalse(popen.killed)

    def test_index_mismatch_in_the_child_asks_for_a_rebuild(self):
        with self.assertRaises(placement.DenseError) as raised:
            self.run_dense(FakePopen("", "Traceback\nIndexMismatch: vettori non allineati", code=1))
        self.assertTrue(raised.exception.rebuild)
        with self.assertRaises(placement.DenseError) as raised:
            self.run_dense(FakePopen("", "MemoryError", code=1))
        self.assertFalse(raised.exception.rebuild)

    def test_child_failures_become_dense_errors(self):
        cases = [FakePopen("", "Traceback\nIndexMismatch: vettori", code=1), FakePopen("non json"),
                 FakePopen(json.dumps({"groups": [["x"]]}))]
        for popen in cases:
            with self.subTest(stdout=popen.stdout), self.assertRaises(placement.DenseError):
                self.run_dense(popen)
        with self.assertRaises(placement.DenseError):
            self.run_dense(FakePopen(), python=None)

    def test_slow_child_is_killed(self):
        popen = FakePopen(hang=True)
        with self.assertRaises(placement.DenseError):
            self.run_dense(popen)
        self.assertTrue(popen.killed)

    def test_warm_up_starts_the_child_only_with_the_venv(self):
        popen = FakePopen(json.dumps({"groups": []}))
        with mock.patch("cc_panel.semantic.python", return_value=None), mock.patch("subprocess.Popen", popen):
            self.assertIsNone(placement.warm_up())
        with mock.patch("cc_panel.semantic.python", return_value="/venv/bin/python"), mock.patch("subprocess.Popen", popen):
            process = placement.warm_up()
        self.assertEqual(popen.kwargs["stdin"], subprocess.PIPE)
        self.assertEqual(process("testo", 1.0), {})
        process.close()
        self.assertFalse(popen.killed)

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evals.loaders import (
    RETRIEVAL_BENCHMARK_PATH,
    dataset_sha256,
    load_retrieval_cases,
    validate_retrieval_cases_against_curriculum,
)
from evals.metrics import (
    hit_rate_at_k,
    paired_bootstrap_ci,
    recall_at_k,
    reciprocal_rank,
)
from evals.schemas import CaseValidationError, RetrievalBenchmarkCase


class TestRetrievalBenchmark(unittest.TestCase):
    def setUp(self):
        self.valid_raw_case = {
            "id": "retrieval-test-01",
            "query": "How do you say hello?",
            "category": "direct_vocab",
            "primary_lesson_id": 1,
            "expected_relevant_slide_ids": ["L1-S2"],
            "expected_relevant_lesson_ids": [1],
            "expected_relevant_skill_ids": ["pronunciation.silent-h", "communication.greetings"],
            "notes": "Direct hello retrieval test case.",
        }

    def tearDown(self):
        sys.modules.pop("evals.adapters.current_rag", None)

    def _write_temp_cases(self, rows: list[dict]) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8", delete=False)
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.close()
        path = Path(handle.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    # --- 1. Schema Validation Tests ---
    def test_schema_valid_case(self):
        case = RetrievalBenchmarkCase.from_dict(self.valid_raw_case)
        self.assertEqual(case.id, "retrieval-test-01")
        self.assertEqual(case.primary_lesson_id, 1)
        self.assertEqual(case.expected_relevant_slide_ids, ("L1-S2",))

    def test_schema_missing_fields_rejected(self):
        bad = dict(self.valid_raw_case)
        del bad["query"]
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    def test_schema_unknown_fields_rejected(self):
        bad = dict(self.valid_raw_case, unknown_field="invalid")
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    def test_schema_invalid_category_rejected(self):
        bad = dict(self.valid_raw_case, category="not_a_category")
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    def test_schema_invalid_lesson_id_rejected(self):
        bad = dict(self.valid_raw_case, primary_lesson_id=99)
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    def test_schema_empty_slides_rejected(self):
        bad = dict(self.valid_raw_case, expected_relevant_slide_ids=[])
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    def test_schema_duplicate_slides_rejected(self):
        bad = dict(self.valid_raw_case, expected_relevant_slide_ids=["L1-S2", "L1-S2"])
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    def test_schema_invalid_slide_format_rejected(self):
        bad = dict(self.valid_raw_case, expected_relevant_slide_ids=["slide-1"])
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(bad)

    # --- 2. Loader & Curriculum Validation Tests ---
    def test_loader_rejects_duplicate_case_id(self):
        path = self._write_temp_cases([self.valid_raw_case, self.valid_raw_case])
        with self.assertRaises(CaseValidationError) as ctx:
            load_retrieval_cases(path)
        self.assertIn("duplicate case id", str(ctx.exception))

    def test_curriculum_validation_rejects_unknown_slide_id(self):
        bad_case = RetrievalBenchmarkCase.from_dict(dict(self.valid_raw_case, expected_relevant_slide_ids=["L1-S999"]))
        with self.assertRaises(CaseValidationError) as ctx:
            validate_retrieval_cases_against_curriculum([bad_case])
        self.assertIn("does not exist in curriculum", str(ctx.exception))

    def test_curriculum_validation_rejects_unknown_skill_id(self):
        bad_case = RetrievalBenchmarkCase.from_dict(dict(self.valid_raw_case, expected_relevant_skill_ids=["not.a.skill"]))
        with self.assertRaises(CaseValidationError) as ctx:
            validate_retrieval_cases_against_curriculum([bad_case])
        self.assertIn("does not exist in curriculum taxonomy", str(ctx.exception))

    def test_benchmark_dataset_integrity(self):
        cases = load_retrieval_cases(RETRIEVAL_BENCHMARK_PATH)
        self.assertGreaterEqual(len(cases), 60, "Must have at least 60 benchmark cases")
        self.assertEqual(len(cases), 75, "Full benchmark dataset must contain exactly 75 cases")

        # Validate all cases against actual curriculum
        validate_retrieval_cases_against_curriculum(cases)

        # Check lesson coverage (all 5 lessons covered)
        lesson_counts = {}
        for c in cases:
            lesson_counts[c.primary_lesson_id] = lesson_counts.get(c.primary_lesson_id, 0) + 1
        self.assertEqual(set(lesson_counts.keys()), {1, 2, 3, 4, 5})
        for lid in range(1, 6):
            self.assertEqual(lesson_counts[lid], 15, f"Lesson {lid} must have 15 cases")

    def test_dataset_sha256_stability(self):
        actual_hash = dataset_sha256(RETRIEVAL_BENCHMARK_PATH)
        self.assertEqual(actual_hash, "6da7edc2002a455a3c95e68fd837e31310799027e1495698aa6550f8a2e6ad4e")

    # --- 3. Metric Calculations & Edge Cases ---
    def test_hit_rate_at_k(self):
        retrieved = ["L1-S1", "L1-S2", "L1-S3"]
        # Hit at 1
        self.assertEqual(hit_rate_at_k(retrieved, {"L1-S1"}, 1), 1.0)
        # Miss at 1, hit at 3
        self.assertEqual(hit_rate_at_k(retrieved, {"L1-S2"}, 1), 0.0)
        self.assertEqual(hit_rate_at_k(retrieved, {"L1-S2"}, 3), 1.0)
        # Miss at 3
        self.assertEqual(hit_rate_at_k(retrieved, {"L1-S10"}, 3), 0.0)
        # Empty relevant IDs
        self.assertEqual(hit_rate_at_k(retrieved, set(), 3), 0.0)
        # Invalid k raises ValueError
        with self.assertRaises(ValueError):
            hit_rate_at_k(retrieved, {"L1-S1"}, 0)

    def test_recall_at_k_single_and_multi_relevance(self):
        retrieved = ["L1-S1", "L1-S2", "L1-S3"]
        # Single gold item
        self.assertEqual(recall_at_k(retrieved, {"L1-S1"}, 1), 1.0)
        self.assertEqual(recall_at_k(retrieved, {"L1-S2"}, 1), 0.0)
        self.assertEqual(recall_at_k(retrieved, {"L1-S2"}, 3), 1.0)

        # Multi-relevance gold items: 2 gold items, 1 found in top 3
        gold_two = {"L1-S2", "L1-S10"}
        self.assertEqual(recall_at_k(retrieved, gold_two, 1), 0.0)
        self.assertEqual(recall_at_k(retrieved, gold_two, 3), 0.5)

        # Multi-relevance gold items: 2 gold items, both found in top 3
        gold_both = {"L1-S1", "L1-S2"}
        self.assertEqual(recall_at_k(retrieved, gold_both, 1), 0.5)
        self.assertEqual(recall_at_k(retrieved, gold_both, 3), 1.0)

        # 4 gold items, 2 found in top 3
        gold_four = {"L1-S1", "L1-S3", "L1-S8", "L1-S10"}
        self.assertEqual(recall_at_k(retrieved, gold_four, 3), 2 / 4)

    def test_reciprocal_rank(self):
        retrieved = ["L1-S1", "L1-S2", "L1-S3"]
        # Rank 1
        self.assertEqual(reciprocal_rank(retrieved, {"L1-S1"}), 1.0)
        # Rank 2
        self.assertEqual(reciprocal_rank(retrieved, {"L1-S2"}), 0.5)
        # Rank 3
        self.assertAlmostEqual(reciprocal_rank(retrieved, {"L1-S3"}), 1 / 3)
        # Rank 4 (outside top 3) -> 0.0
        self.assertEqual(reciprocal_rank(retrieved, {"L1-S4"}), 0.0)
        # Multi-relevance: uses rank of first relevant result
        self.assertEqual(reciprocal_rank(retrieved, {"L1-S2", "L1-S3"}), 0.5)

    # --- 4. Paired Bootstrap Confidence Interval ---
    def test_paired_bootstrap_ci_positive_shift(self):
        # A has scores 0.0, B has scores 1.0
        scores_a = [0.0] * 50
        scores_b = [1.0] * 50
        res = paired_bootstrap_ci(scores_a, scores_b, num_resamples=500, seed=42)
        self.assertEqual(res["mean_delta"], 1.0)
        self.assertEqual(res["ci_lower"], 1.0)
        self.assertEqual(res["ci_upper"], 1.0)
        self.assertTrue(res["significant"])

    def test_paired_bootstrap_ci_zero_shift(self):
        # Identical scores
        scores = [0.5] * 50
        res = paired_bootstrap_ci(scores, scores, num_resamples=500, seed=42)
        self.assertEqual(res["mean_delta"], 0.0)
        self.assertEqual(res["ci_lower"], 0.0)
        self.assertEqual(res["ci_upper"], 0.0)
        self.assertFalse(res["significant"])

    def test_paired_bootstrap_ci_length_mismatch_raises(self):
        with self.assertRaises(ValueError):
            paired_bootstrap_ci([1.0], [1.0, 2.0])

    # --- 5. Production Retrieval Adapter Fidelity ---
    def test_adapter_delegates_to_production_legacy_semantic(self):
        from evals.adapters.current_rag import retrieve_legacy
        with patch("evals.adapters.current_rag.legacy_semantic") as mock_legacy:
            mock_slide = MagicMock()
            mock_slide.slide_id = "L1-S2"
            mock_legacy.return_value = [mock_slide]

            mock_db = MagicMock()
            dummy_vector = [0.1] * 768

            result = retrieve_legacy(mock_db, dummy_vector)
            self.assertEqual(result, ["L1-S2"])
            mock_legacy.assert_called_once_with(mock_db, dummy_vector)

    def test_adapter_delegates_to_production_hybrid(self):
        from evals.adapters.current_rag import retrieve_hybrid_variant
        with patch("evals.adapters.current_rag.hybrid") as mock_hybrid:
            mock_slide = MagicMock()
            mock_slide.slide_id = "L1-S6"
            mock_hybrid.return_value = [mock_slide]

            mock_db = MagicMock()
            dummy_vector = [0.1] * 768

            result = retrieve_hybrid_variant(mock_db, "Buenos dias", dummy_vector)
            self.assertEqual(result, ["L1-S6"])
            mock_hybrid.assert_called_once()

    def test_adapter_delegates_to_production_targeted_oracle(self):
        from evals.adapters.current_rag import retrieve_targeted_oracle_variant
        with patch("evals.adapters.current_rag.semantic_metadata") as mock_meta:
            mock_slide = MagicMock()
            mock_slide.slide_id = "L1-S8"
            mock_meta.return_value = [mock_slide]

            mock_db = MagicMock()
            dummy_vector = [0.1] * 768

            result = retrieve_targeted_oracle_variant(mock_db, dummy_vector, "grammar.gender-agreement")
            self.assertEqual(result, ["L1-S8"])
            mock_meta.assert_called_once()

    # --- 6. Read-Only Safety ---
    def test_read_only_safety_no_mutations_allowed(self):
        from evals.adapters.current_rag import retrieve_legacy
        mock_db = MagicMock()
        dummy_vector = [0.1] * 768
        with patch("evals.adapters.current_rag.legacy_semantic", return_value=[]):
            retrieve_legacy(mock_db, dummy_vector)
        # Verify db was never asked to commit, flush, add, or delete
        mock_db.commit.assert_not_called()
        mock_db.flush.assert_not_called()
        mock_db.add.assert_not_called()
        mock_db.delete.assert_not_called()

    # --- 7. Runtime Configuration & Fairness Metadata ---
    def test_runtime_configuration_metadata(self):
        from evals.adapters.current_rag import runtime_configuration
        config = runtime_configuration()
        self.assertEqual(config["provider"], "Google Gemini")
        self.assertEqual(config["legacy_top_k"], 3)
        self.assertEqual(config["legacy_max_cosine_distance"], 0.65)
        self.assertIn("legacy_semantic", str(config["retrieval_mode"]))



if __name__ == "__main__":
    unittest.main()

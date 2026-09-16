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
    abstention_accuracy,
    false_positive_rate,
    hit_rate_at_k,
    is_correct_abstention,
    is_false_positive,
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

    def test_schema_valid_negative_case(self):
        raw_negative = {
            "id": "retrieval-neg-test-01",
            "query": "how do I configure a PostgreSQL database",
            "category": "out_of_scope_negative",
            "primary_lesson_id": None,
            "expected_relevant_slide_ids": [],
            "expected_relevant_lesson_ids": [],
            "expected_relevant_skill_ids": [],
            "notes": "Negative out of scope test case.",
        }
        case = RetrievalBenchmarkCase.from_dict(raw_negative)
        self.assertEqual(case.id, "retrieval-neg-test-01")
        self.assertIsNone(case.primary_lesson_id)
        self.assertTrue(case.is_negative)
        self.assertEqual(case.expected_relevant_slide_ids, ())

    def test_schema_negative_case_with_non_null_lesson_rejected(self):
        raw = {
            "id": "retrieval-neg-test-02",
            "query": "test query",
            "category": "out_of_scope_negative",
            "primary_lesson_id": 1,
            "expected_relevant_slide_ids": [],
            "expected_relevant_lesson_ids": [],
            "expected_relevant_skill_ids": [],
            "notes": "Negative test with lesson.",
        }
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(raw)

    def test_schema_negative_case_with_wrong_category_rejected(self):
        raw = {
            "id": "retrieval-neg-test-03",
            "query": "test query",
            "category": "direct_vocab",
            "primary_lesson_id": None,
            "expected_relevant_slide_ids": [],
            "expected_relevant_lesson_ids": [],
            "expected_relevant_skill_ids": [],
            "notes": "Negative test with wrong category.",
        }
        with self.assertRaises(CaseValidationError):
            RetrievalBenchmarkCase.from_dict(raw)

    def test_schema_positive_empty_slides_rejected(self):
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
        self.assertEqual(len(cases), 85, "Full benchmark dataset must contain exactly 85 cases (75 positive + 10 negative)")

        # Validate all cases against actual curriculum
        validate_retrieval_cases_against_curriculum(cases)

        positives = [c for c in cases if not c.is_negative]
        negatives = [c for c in cases if c.is_negative]
        self.assertEqual(len(positives), 75)
        self.assertEqual(len(negatives), 10)

        # Check lesson coverage on positive cases (all 5 lessons covered, exactly 15 per lesson)
        lesson_counts = {}
        for c in positives:
            self.assertIsNotNone(c.primary_lesson_id)
            lesson_counts[c.primary_lesson_id] = lesson_counts.get(c.primary_lesson_id, 0) + 1
        self.assertEqual(set(lesson_counts.keys()), {1, 2, 3, 4, 5})
        for lid in range(1, 6):
            self.assertEqual(lesson_counts[lid], 15, f"Lesson {lid} must have 15 positive cases")

        # Check negative cases have primary_lesson_id=None and category out_of_scope_negative
        for c in negatives:
            self.assertIsNone(c.primary_lesson_id)
            self.assertEqual(c.category, "out_of_scope_negative")
            self.assertEqual(c.expected_relevant_slide_ids, ())

    def test_dataset_sha256_stability(self):
        actual_hash = dataset_sha256(RETRIEVAL_BENCHMARK_PATH)
        self.assertEqual(actual_hash, "62be522d7e123517449c5a2959b29aab29375189a21b4836d7f0632db1592c25")

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
        # Empty relevant IDs raises ValueError (negative cases use abstention metrics)
        with self.assertRaises(ValueError):
            hit_rate_at_k(retrieved, set(), 3)
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

        # Empty relevant IDs raises ValueError
        with self.assertRaises(ValueError):
            recall_at_k(retrieved, set(), 3)

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
        # Empty relevant IDs raises ValueError
        with self.assertRaises(ValueError):
            reciprocal_rank(retrieved, set())

    def test_negative_abstention_metrics(self):
        # Correct abstention: 0 slides returned
        self.assertTrue(is_correct_abstention([]))
        self.assertFalse(is_false_positive([]))

        # False positive: 1 or more slides returned
        self.assertFalse(is_correct_abstention(["L1-S1"]))
        self.assertTrue(is_false_positive(["L1-S1"]))
        self.assertFalse(is_correct_abstention(["L1-S1", "L1-S2"]))
        self.assertTrue(is_false_positive(["L1-S1", "L1-S2"]))

        # Aggregate metrics
        all_abstained = [[], [], []]
        self.assertEqual(abstention_accuracy(all_abstained), 1.0)
        self.assertEqual(false_positive_rate(all_abstained), 0.0)

        mixed = [[], ["L1-S1"], [], ["L2-S3"]]
        self.assertEqual(abstention_accuracy(mixed), 0.5)
        self.assertEqual(false_positive_rate(mixed), 0.5)

        # Empty list
        self.assertEqual(abstention_accuracy([]), 0.0)
        self.assertEqual(false_positive_rate([]), 0.0)

    # --- 4. Paired Bootstrap Confidence Interval ---
    def test_paired_bootstrap_ci_positive_shift(self):
        # A has scores 0.0, B has scores 1.0
        scores_a = [0.0] * 50
        scores_b = [1.0] * 50
        res = paired_bootstrap_ci(scores_a, scores_b, num_resamples=500, seed=42)
        self.assertEqual(res["mean_delta"], 1.0)
        self.assertEqual(res["ci_lower"], 1.0)
        self.assertEqual(res["ci_upper"], 1.0)
        self.assertTrue(res["ci_excludes_zero"])
        self.assertTrue(res["significant"])

    def test_paired_bootstrap_ci_zero_shift(self):
        # Identical scores
        scores = [0.5] * 50
        res = paired_bootstrap_ci(scores, scores, num_resamples=500, seed=42)
        self.assertEqual(res["mean_delta"], 0.0)
        self.assertEqual(res["ci_lower"], 0.0)
        self.assertEqual(res["ci_upper"], 0.0)
        self.assertFalse(res["ci_excludes_zero"])
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

    # --- 8. Actual SQLAlchemy Table Names ---
    def test_actual_sqlalchemy_table_names(self):
        """Verify actual SQLAlchemy __tablename__ values match app.models without conceptual confusion."""
        from app.models import (
            AssessmentEvent,
            LearnerSkillState,
            LessonSlide,
            LessonSlideSkill,
            PracticeAttempt,
            ReviewHistory,
            ReviewItem,
            Skill,
        )
        self.assertEqual(Skill.__tablename__, "skills")
        self.assertEqual(LessonSlideSkill.__tablename__, "lesson_slide_skills")
        self.assertEqual(LessonSlide.__tablename__, "lesson_slides")
        self.assertEqual(LearnerSkillState.__tablename__, "learner_skill_states")
        self.assertEqual(AssessmentEvent.__tablename__, "assessment_events")
        self.assertEqual(PracticeAttempt.__tablename__, "practice_attempts")
        self.assertEqual(ReviewItem.__tablename__, "review_items")
        self.assertEqual(ReviewHistory.__tablename__, "review_history")

        # Explicitly verify conceptual aliases are NOT actual table names
        actual_tables = {
            Skill.__tablename__,
            LessonSlideSkill.__tablename__,
            LessonSlide.__tablename__,
            LearnerSkillState.__tablename__,
            AssessmentEvent.__tablename__,
            PracticeAttempt.__tablename__,
            ReviewItem.__tablename__,
            ReviewHistory.__tablename__,
        }
        self.assertNotIn("curriculum_skills", actual_tables)
        self.assertNotIn("slide_skills", actual_tables)
        self.assertNotIn("learner_profiles", actual_tables)
        self.assertNotIn("mastery_audit_log", actual_tables)
        self.assertNotIn("fsrs_cards", actual_tables)

    # --- 9. Authoritative Lesson Titles Derivation ---
    def test_authoritative_lesson_titles_derivation(self):
        """Verify lesson titles are derived from authoritative curriculum source."""
        from evals.loaders import get_authoritative_lesson_titles
        titles = get_authoritative_lesson_titles()
        expected_titles = {
            1: "The Ultimate Greeting Masterclass",
            2: "The Magic Verbs (Survival Mode)",
            3: "Polite & Thirsty (Dining 101)",
            4: "Where is it? (The GPS Module)",
            5: "The Ultimate Café Simulation (RPG Mode)",
        }
        self.assertEqual(titles, expected_titles)

        # Stale invented/paraphrased titles must NOT be present
        stale_titles = {
            "¡Mucho Gusto!",
            "La Comida y el Restaurante",
            "La Familia y la Rutina",
            "Por la Ciudad y los Viajes",
            "El Café y la Conversación",
            "Greetings & Basics",
            "Future & Career",
        }
        for stale in stale_titles:
            self.assertNotIn(stale, set(titles.values()))

    # --- 10. Targeted Oracle Negative Metric Representation ---
    def test_targeted_oracle_negative_abstention_is_not_applicable(self):
        """targeted_oracle negative abstention must be reported as NOT APPLICABLE, never a fake 1.0 / 100%."""
        from evals.run_eval import retrieval_benchmark_report
        mock_db = MagicMock()
        mock_scalar = MagicMock(return_value=1)
        mock_db.scalar = mock_scalar
        mock_db.execute.return_value.all.return_value = []
        mock_db.execute.return_value.scalar.return_value = "0.8.1"

        pos_case = RetrievalBenchmarkCase.from_dict(self.valid_raw_case)
        neg_case = RetrievalBenchmarkCase.from_dict({
            "id": "retrieval-neg-test-01",
            "query": "how do I configure a PostgreSQL database",
            "category": "out_of_scope_negative",
            "primary_lesson_id": None,
            "expected_relevant_slide_ids": [],
            "expected_relevant_lesson_ids": [],
            "expected_relevant_skill_ids": [],
            "notes": "Negative out of scope test case.",
        })

        with patch("evals.run_eval.load_retrieval_cases", return_value=[pos_case, neg_case]), \
             patch("evals.run_eval.validate_retrieval_cases_against_curriculum"), \
             patch("app.database.SessionLocal", return_value=mock_db), \
             patch("evals.adapters.current_rag.embed_query", return_value=[0.1] * 768), \
             patch("evals.adapters.current_rag.retrieve_legacy", return_value=["L1-S1"]), \
             patch("evals.adapters.current_rag.retrieve_hybrid_variant", return_value=["L1-S1"]), \
             patch("evals.adapters.current_rag.retrieve_targeted_oracle_variant", return_value=[]):
            report = retrieval_benchmark_report(
                variants=["targeted_oracle", "B_legacy"],
            )
            oracle_neg = report["metrics_by_variant"]["targeted_oracle"]["negative_abstention_metrics"]
            self.assertEqual(oracle_neg["abstention_accuracy"], "NOT APPLICABLE")
            self.assertEqual(oracle_neg["false_positive_rate"], "NOT APPLICABLE")
            self.assertEqual(oracle_neg["mean_incorrect_slides_returned"], "NOT APPLICABLE")
            self.assertIn("oracle-conditioned experiment", oracle_neg["note"])

            # Legacy baseline must still report numeric metrics
            legacy_neg = report["metrics_by_variant"]["B_legacy"]["negative_abstention_metrics"]
            self.assertIsInstance(legacy_neg["abstention_accuracy"], float)
            self.assertIsInstance(legacy_neg["false_positive_rate"], float)

    # --- 11. Machine-Readable Report Schema & Freshness Metadata ---
    def test_benchmark_report_metadata_and_freshness(self):
        """Verify report JSON (if generated) contains consistent dataset hash, counts, and metadata."""
        report_path = Path(__file__).resolve().parent.parent / "evals" / "reports" / "retrieval_benchmark.json"
        if not report_path.exists():
            self.skipTest("evals/reports/retrieval_benchmark.json not present in local checkout")

        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report_data["total_case_count"], 85)
        self.assertEqual(report_data["positive_case_count"], 75)
        self.assertEqual(report_data["negative_case_count"], 10)
        self.assertEqual(
            report_data["dataset_sha256"],
            "62be522d7e123517449c5a2959b29aab29375189a21b4836d7f0632db1592c25",
        )
        self.assertEqual(report_data["database_metadata"]["slide_count"], 231)
        self.assertEqual(report_data["database_metadata"]["skill_count"], 14)
        self.assertEqual(report_data["database_metadata"]["pgvector_version"], "0.8.1")
        self.assertEqual(report_data["database_metadata"]["tables"]["curriculum_skills"], "skills")
        self.assertEqual(report_data["database_metadata"]["tables"]["slide_skill_associations"], "lesson_slide_skills")

        # Verify oracle negative abstention is NOT APPLICABLE in report
        oracle_metrics = report_data["metrics_by_variant"]["targeted_oracle"]
        self.assertEqual(oracle_metrics["negative_abstention_metrics"]["abstention_accuracy"], "NOT APPLICABLE")
        self.assertEqual(oracle_metrics["negative_abstention_metrics"]["false_positive_rate"], "NOT APPLICABLE")

        # Verify lesson titles are derived properly in report breakdowns
        for var in report_data["metrics_by_variant"].values():
            self.assertEqual(var["lesson_breakdown"]["1"]["lesson_title"], "The Ultimate Greeting Masterclass")
            self.assertEqual(var["lesson_breakdown"]["2"]["lesson_title"], "The Magic Verbs (Survival Mode)")
            self.assertEqual(var["lesson_breakdown"]["3"]["lesson_title"], "Polite & Thirsty (Dining 101)")
            self.assertEqual(var["lesson_breakdown"]["4"]["lesson_title"], "Where is it? (The GPS Module)")
            self.assertEqual(var["lesson_breakdown"]["5"]["lesson_title"], "The Ultimate Café Simulation (RPG Mode)")


if __name__ == "__main__":
    unittest.main()

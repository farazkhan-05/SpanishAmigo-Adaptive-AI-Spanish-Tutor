import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evals.baseline import baseline_configuration, validate_baseline_configuration
from evals.loaders import DEFAULT_CASES_PATH, load_cases
from evals.metrics import recall_at_k, reciprocal_rank
from evals.run_eval import offline_report


class EvaluationTests(unittest.TestCase):
    def _write_cases(self, rows):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", encoding="utf-8", delete=False)
        for row in rows:
            handle.write(json.dumps(row) + "\n")
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_malformed_case_is_rejected(self):
        path = self._write_cases([{"id": "bad"}])
        with self.assertRaises(ValueError):
            load_cases(path)

    def test_duplicate_ids_are_rejected(self):
        row = {"id": "same", "category": "x", "user_input": "x", "expected_behavior": "allowed", "assessable_production": False, "notes": "x"}
        with self.assertRaises(ValueError):
            load_cases(self._write_cases([row, row]))

    def test_invalid_label_is_rejected(self):
        row = {"id": "bad-label", "category": "x", "user_input": "x", "expected_behavior": "maybe", "assessable_production": False, "notes": "x"}
        with self.assertRaises(ValueError):
            load_cases(self._write_cases([row]))

    def test_recall_at_k_known_example(self):
        self.assertEqual(recall_at_k(["x", "a", "b"], {"a", "b"}, 2), 0.5)

    def test_mrr_known_example(self):
        self.assertEqual(reciprocal_rank(["x", "y", "a"], {"a", "b"}), 1 / 3)

    def test_offline_report_is_deterministic_and_does_not_import_adapter(self):
        first = offline_report(DEFAULT_CASES_PATH)
        second = offline_report(DEFAULT_CASES_PATH)
        self.assertEqual(first, second)
        self.assertNotIn("evals.adapters.current_rag", sys.modules)

    def test_baseline_configuration_is_valid(self):
        validate_baseline_configuration(baseline_configuration())


if __name__ == "__main__":
    unittest.main()

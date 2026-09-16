import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from app.services import telemetry


class TelemetryTests(unittest.TestCase):
    def test_missing_provider_metadata_is_null_not_estimated(self):
        self.assertEqual(telemetry.token_fields(None), {"input_tokens": None, "output_tokens": None, "total_tokens": None})

    def test_percentiles_are_descriptive_nearest_rank_values(self):
        self.assertEqual(telemetry.percentile([1, 2, 3, 4, 100], 50), 3)
        self.assertEqual(telemetry.percentile([1, 2, 3, 4, 100], 95), 100)

    def test_ttft_ignores_session_empty_and_tool_events_and_sets_once(self):
        stamp = None
        stamp = telemetry.first_token_timestamp(stamp, "", 1.0)
        stamp = telemetry.first_token_timestamp(stamp, "", 2.0)
        stamp = telemetry.first_token_timestamp(stamp, "Hola", 3.0)
        stamp = telemetry.first_token_timestamp(stamp, " amigo", 4.0)
        self.assertEqual(stamp, 3.0)

    def test_writer_does_not_accept_or_persist_content_fields(self):
        with patch("app.services.telemetry.SessionLocal", side_effect=RuntimeError("db down")):
            telemetry.record(operation_id="x", operation="chat", message="learner secret", content="assistant secret")

    @patch("app.services.telemetry.random.random", return_value=0.99)
    @patch("app.services.telemetry.SessionLocal")
    def test_failures_bypass_success_sampling(self, session_local, _random):
        telemetry.record(operation_id="x", operation="chat", success=False, error_category="provider_error")
        session_local.assert_called_once()

    @patch("app.services.telemetry.random.random", return_value=0.99)
    @patch("app.services.telemetry.SessionLocal")
    @patch("app.services.telemetry.get_settings")
    def test_success_events_are_sampled(self, settings, session_local, _random):
        settings.return_value.TELEMETRY_ENABLED = True
        settings.return_value.TELEMETRY_SAMPLE_RATE = 0.5
        telemetry.record(operation_id="x", operation="chat", success=True)
        session_local.assert_not_called()

    def test_failure_categories(self):
        self.assertEqual(telemetry.error_category(Exception("429 quota exceeded")), "provider_quota")
        self.assertEqual(telemetry.error_category(TimeoutError()), "provider_timeout")

    def test_prune_uses_configured_retention(self):
        class Result: rowcount = 2
        class Db:
            def execute(self, _): return Result()
            def commit(self): pass
        self.assertEqual(telemetry.prune(Db(), 1), 2)

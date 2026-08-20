import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import monitor_dashboard_auth as monitor


class MonitorDashboardAuthTests(unittest.TestCase):
    def test_evaluate_marks_403_bootstrap_as_degraded(self):
        with patch.object(monitor, "request_status", side_effect=[200, 403]):
            result = monitor.evaluate()
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.readiness_status, 200)
        self.assertEqual(result.clerk_bootstrap_status, 403)

    def test_alert_text_has_technical_status_only(self):
        text = monitor.technical_text(monitor.MonitorResult("degraded", 200, 403), False)
        self.assertIn("http-403", text)
        self.assertNotIn("CV", text)
        self.assertNotIn("candidate@", text)

    def test_state_round_trip_uses_no_personal_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            result = monitor.MonitorResult("healthy", 200, 200)
            monitor.persist(result, path)
            self.assertEqual(monitor.load_previous_status(path), "healthy")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(payload), {"status", "readiness_status", "clerk_bootstrap_status", "updated_at"})

    def test_sentry_envelope_is_redacted(self):
        response = Mock(ok=True)
        with patch.object(monitor.requests, "get", return_value=Mock(json=lambda: {"dsn": "https://public@example.ingest.sentry.io/42"})), patch.object(monitor.requests, "post", return_value=response) as post:
            self.assertTrue(monitor.report_sentry(monitor.MonitorResult("degraded", 200, 403), False))
        sent = post.call_args.kwargs["data"]
        self.assertIn("technical-only", sent)
        self.assertNotIn("candidate@", sent)
        self.assertNotIn("CV", sent)


if __name__ == "__main__":
    unittest.main()

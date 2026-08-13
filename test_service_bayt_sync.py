#!/usr/bin/env python3
"""Local HTTP test for Bayt queue visibility and authenticated lead synchronization."""
from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class ServiceBaytSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        os.environ["DB_PATH"] = str(Path(self.temp.name) / "service.db")
        os.environ["JOB_IMPORT_TOKEN"] = "unit-test-import-token"
        os.environ["BAYT_BROWSER_PROFILE_READY"] = "true"
        import db
        import service
        self.db = importlib.reload(db)
        self.service = importlib.reload(service)
        self.server = self.service.build_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()
        for key in ("DB_PATH", "JOB_IMPORT_TOKEN", "BAYT_BROWSER_PROFILE_READY"):
            os.environ.pop(key, None)

    def _request(self, path: str, *, body: dict | None = None, token: str | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        if token:
            headers["X-Job-Import-Token"] = token
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_auditor_review_bridge_is_protected_and_non_submitting(self) -> None:
        body = {"system_prompt": "Return the required JSON schema.", "package": {"job": {"role": "Coordinator"}}}
        status, payload = self._request("/v1/admin/auditor/review", body=body)
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])

        from unittest.mock import patch
        response = {"decision": "approve", "confidence": 0.95, "reasons": ["supported"], "required_fixes": []}
        with patch("auditor.configured_ai_reviewer", return_value=response):
            status, payload = self._request("/v1/admin/auditor/review", body=body, token="unit-test-import-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "review": response})

    def test_auditor_self_test_is_protected_and_non_submitting(self) -> None:
        status, payload = self._request("/v1/admin/auditor/self-test", body={})
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])

        from unittest.mock import patch
        with patch("auditor.configured_ai_reviewer", return_value={"decision": "approve", "confidence": 1.0, "reasons": ["connectivity"], "required_fixes": []}):
            status, payload = self._request("/v1/admin/auditor/self-test", body={}, token="unit-test-import-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "reviewer": "available", "schema_valid": True})

    def test_import_is_authenticated_and_bayt_only(self) -> None:
        status, payload = self._request("/v1/admin/jobs/import", body={"jobs": [{"title": "Barista", "company": "Example", "url": "https://www.bayt.com/en/saudi-arabia/jobs/barista-1/"}]})
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])

        jobs = [
            {"title": "Barista", "company": "Example", "location": "Riyadh", "url": "https://www.bayt.com/en/saudi-arabia/jobs/barista-1/", "category": "service_and_entry", "status": "new"},
            {"title": "Other", "company": "Example", "location": "Riyadh", "url": "https://example.com/jobs/2", "category": "other", "status": "new"},
        ]
        status, payload = self._request("/v1/admin/jobs/import", body={"jobs": jobs}, token="unit-test-import-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload["import"]["inserted"], 2)
        self.assertFalse(payload["external_execution_enabled"])

        status, queue = self._request("/v1/portal-queues/bayt")
        self.assertEqual(status, 200)
        self.assertEqual(queue["bayt"]["total_bayt_leads"], 1)
        self.assertEqual(queue["bayt"]["by_route_status"]["browser_handoff_ready"], 1)
        self.assertEqual(queue["bayt"]["execution_mode"], "browser_handoff_only")

    def test_browser_outcome_recorder_is_authenticated_and_non_submitting(self) -> None:
        outcome = {
            "url": "https://www.bayt.com/en/saudi-arabia/jobs/timeout-1/",
            "status": "browser_timeout",
            "detail": "extension timeout",
        }
        status, payload = self._request("/v1/admin/portal-handoffs/outcomes", body=outcome)
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])

        status, payload = self._request(
            "/v1/admin/portal-handoffs/outcomes", body=outcome, token="unit-test-import-token"
        )
        self.assertEqual(status, 200)
        self.assertFalse(payload["submits_applications"])
        self.assertEqual(payload["record"]["status"], "browser_timeout")
        self.assertEqual(payload["record"]["attempt_count"], 1)

    def test_diversified_queue_is_read_only_and_employer_balanced(self) -> None:
        jobs = [
            {"title": "Barista", "company": "Same Employer", "location": "Riyadh", "url": "https://www.bayt.com/en/saudi-arabia/jobs/barista-diverse-1/", "category": "service_and_entry", "status": "new"},
            {"title": "Waiter", "company": "Same Employer", "location": "Riyadh", "url": "https://www.bayt.com/en/saudi-arabia/jobs/waiter-diverse-2/", "category": "service_and_entry", "status": "new"},
            {"title": "Customer Service Agent", "company": "Other Employer", "location": "Jeddah", "url": "https://jobs.ashbyhq.com/other/jobs/3", "category": "service_and_entry", "status": "new"},
            {"title": "Administrative Assistant", "company": "Third Employer", "location": "Dammam", "url": "https://job-boards.greenhouse.io/third/jobs/4", "category": "administrative", "status": "new"},
        ]
        status, imported = self._request("/v1/admin/jobs/import", body={"jobs": jobs}, token="unit-test-import-token")
        self.assertEqual(status, 200)
        self.assertEqual(imported["import"]["inserted"], 4)

        status, payload = self._request("/v1/portal-queues/diversified?limit=4")
        self.assertEqual(status, 200)
        queue = payload["queue"]
        self.assertFalse(queue["submits_applications"])
        self.assertEqual(queue["execution_mode"], "browser_handoff_only")
        self.assertLessEqual(queue["selected_by_source"].get("bayt", 0), 2)
        self.assertEqual(sum(1 for item in queue["selected"] if item["company"] == "Same Employer"), 1)
        self.assertTrue(all("REQUIRE" in item["handoff_reason"] or "READY" in item["handoff_reason"] for item in queue["selected"]))


if __name__ == "__main__":
    unittest.main()

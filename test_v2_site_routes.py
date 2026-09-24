from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import db
import service


class V2SiteRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_db_path = db.DB_PATH
        db.DB_PATH = str(self.root / "v2.db")
        db.initialize()
        self.server = service.build_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        db.DB_PATH = self.original_db_path
        self.temp.cleanup()

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request_headers = {"Content-Type": "application/json"} if payload is not None else {}
        request_headers.update(headers or {})
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=payload,
            method=method,
            headers=request_headers,
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "{}"), dict(response.headers)
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}"), dict(exc.headers)

    def test_health_alias_matches_site_probe(self) -> None:
        status, payload, _headers = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("metrics", payload)

    def test_dashboard_origin_gets_cors_headers(self) -> None:
        status, _payload, headers = self.request("GET", "/health", headers={"Origin": "https://dashboard.hsndm.tech"})
        self.assertEqual(status, 200)
        self.assertEqual("https://dashboard.hsndm.tech", headers.get("Access-Control-Allow-Origin"))

    def test_recommended_jobs_returns_live_rows_for_signed_in_user(self) -> None:
        db.import_discovered_jobs(
            [
                {
                    "title": "Operations Coordinator",
                    "company": "Example Logistics",
                    "location": "Jeddah",
                    "url": "https://example.com/jobs/ops",
                    "description": "Operations role in Jeddah",
                    "category": "operations",
                    "status": "new",
                }
            ]
        )
        with patch.object(service, "_supabase_user", return_value=({"id": "user-123"}, "", 200)):
            status, payload, _headers = self.request("GET", "/api/v2/jobs/recommended?city=Jeddah&role=Operations")
        self.assertEqual(status, 200)
        self.assertEqual("live", payload["mode"])
        self.assertEqual("Example Logistics", payload["jobs"][0]["companyName"])
        self.assertEqual("user-123", payload["userId"])

    def test_simple_site_email_form_gets_clear_audit_required_response(self) -> None:
        body = {
            "toEmail": "hr@example.com",
            "companyName": "Example",
            "roleTitle": "Operations Coordinator",
            "city": "Jeddah",
            "candidateName": "Candidate",
            "candidateEmail": "candidate@example.com",
            "message": "Hello",
        }
        with patch.object(service, "_supabase_user", return_value=({"id": "user-123"}, "", 200)):
            status, payload, _headers = self.request("POST", "/api/v2/applications/send-email", body)
        self.assertEqual(status, 422)
        self.assertEqual("auditor-package-required", payload["error"])
        self.assertFalse(payload["sent"])


if __name__ == "__main__":
    unittest.main()

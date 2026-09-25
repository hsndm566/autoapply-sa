from __future__ import annotations

import json
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

    def test_v2_health_is_public_and_specific(self) -> None:
        status, payload, _headers = self.request("GET", "/api/v2/health")
        self.assertEqual(status, 200)
        self.assertEqual("autoapply-v2", payload["service"])

    def test_auth_health_reports_supabase_configuration(self) -> None:
        with patch.object(service.v2_site, "_supabase_config", return_value=("https://example.supabase.co", "key")):
            status, payload, _headers = self.request("GET", "/healthz/auth")
        self.assertEqual(status, 200)
        self.assertEqual("ready", payload["status"])

    def test_canonical_v2_origins_get_cors_headers(self) -> None:
        for origin in ("https://www.hsndm.tech", "https://dashboard.hsndm.tech", "https://app.hsndm.tech"):
            status, _payload, headers = self.request("GET", "/api/v2/health", headers={"Origin": origin})
            self.assertEqual(status, 200)
            self.assertEqual(origin, headers.get("Access-Control-Allow-Origin"))

    def test_recommended_jobs_uses_verified_supabase_feed_for_signed_in_user(self) -> None:
        jobs = [{
            "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
            "companyName": "Example Logistics",
            "roleTitle": "Operations Coordinator",
            "city": "Jeddah",
            "source": "public_ats",
            "url": "https://example.com/jobs/ops",
            "summary": "Operations role in Jeddah",
            "matchReason": "title aligns with Operations",
            "freshness": "2026-09-25T18:10:05Z",
        }]
        with (
            patch.object(service, "_supabase_user", return_value=({"id": "user-123"}, "", 200)),
            patch.object(service.v2_site, "recommended_jobs", return_value=jobs) as recommended,
        ):
            status, payload, _headers = self.request(
                "GET",
                "/api/v2/jobs/recommended?city=Jeddah&role=Operations",
                headers={"Authorization": "Bearer test-token"},
            )
        self.assertEqual(status, 200)
        self.assertEqual("live", payload["mode"])
        self.assertEqual("Example Logistics", payload["jobs"][0]["companyName"])
        self.assertEqual("user-123", payload["userId"])
        recommended.assert_called_once_with("test-token", city="Jeddah", role="Operations")

    def test_application_readiness_requires_auth_and_reports_provider_state(self) -> None:
        with (
            patch.object(service, "_supabase_user", return_value=({"id": "user-123"}, "", 200)),
            patch.object(service.v2_site, "readiness", return_value={"ok": True, "status": 200}),
        ):
            status, payload, _headers = self.request(
                "GET",
                "/api/v2/applications/readiness",
                headers={"Authorization": "Bearer test-token"},
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_v2_send_accepts_only_server_reconciled_result(self) -> None:
        result = {
            "ok": True,
            "messageId": "<provider-message-1>",
            "application": {
                "id": "application-1",
                "status": "applied",
                "providerMessageId": "<provider-message-1>",
            },
        }
        with (
            patch.object(service, "_supabase_user", return_value=({"id": "user-123", "email": "candidate@example.com"}, "", 200)),
            patch.object(service.v2_site, "send_application", return_value=result) as send,
        ):
            status, payload, _headers = self.request(
                "POST",
                "/api/v2/applications/send-email",
                {
                    "toEmail": "hr@example.com",
                    "jobId": "199945cc-4e96-451c-bb4f-e999f37c6873",
                },
                headers={"Authorization": "Bearer test-token"},
            )
        self.assertEqual(status, 200)
        self.assertEqual("<provider-message-1>", payload["messageId"])
        self.assertEqual("<provider-message-1>", payload["application"]["providerMessageId"])
        send.assert_called_once_with(
            "test-token",
            {"id": "user-123", "email": "candidate@example.com"},
            to_email="hr@example.com",
            job_id="199945cc-4e96-451c-bb4f-e999f37c6873",
        )

    def test_v2_send_rejects_missing_verified_job_id(self) -> None:
        with patch.object(service, "_supabase_user", return_value=({"id": "user-123"}, "", 200)):
            status, payload, _headers = self.request(
                "POST",
                "/api/v2/applications/send-email",
                {"toEmail": "hr@example.com"},
            )
        self.assertEqual(status, 400)
        self.assertEqual("invalid-application-email", payload["error"])


if __name__ == "__main__":
    unittest.main()

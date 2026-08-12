from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import campaign_worker
import db
import service


class Upload:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self.file = io.BytesIO(content)


class CampaignPlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.original_db_path = db.DB_PATH
        self.original_cv_dir = service.CV_STORAGE_DIR
        self.original_admin = service.ADMIN_API_TOKEN
        self.original_execution = service.ALLOW_LEGACY_EXTERNAL_EXECUTION
        db.DB_PATH = str(self.root / "platform.db")
        service.CV_STORAGE_DIR = self.root / "cv"
        service.ADMIN_API_TOKEN = "test-admin-token"
        service.ALLOW_LEGACY_EXTERNAL_EXECUTION = False
        db.initialize()
        self.server = service.build_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()
        db.DB_PATH = self.original_db_path
        service.CV_STORAGE_DIR = self.original_cv_dir
        service.ADMIN_API_TOKEN = self.original_admin
        service.ALLOW_LEGACY_EXTERNAL_EXECUTION = self.original_execution

    def request(self, method: str, path: str, body: dict | None = None, headers: dict | None = None):
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        all_headers = {"Content-Type": "application/json"} if payload is not None else {}
        all_headers.update(headers or {})
        request = Request(f"http://127.0.0.1:{self.port}{path}", data=payload, method=method, headers=all_headers)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def multipart_request(self, path: str, fields: dict[str, str], filename: str, content: bytes):
        boundary = "----AutoApplyCampaignTestBoundary"
        parts: list[bytes] = []
        for key, value in fields.items():
            parts.extend([
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ])
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="cv"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/pdf\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=b"".join(parts),
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_cv_storage_rejects_invalid_type_and_records_pdf(self):
        with self.assertRaises(ValueError):
            service._store_cv(Upload("malware.exe", b"not a CV"))
        path, original_name, digest = service._store_cv(Upload("candidate.pdf", b"%PDF-1.4 campaign test"))
        self.assertEqual(original_name, "candidate.pdf")
        self.assertTrue(path and Path(path).exists())
        self.assertEqual(len(digest or ""), 64)

    def test_campaign_api_creates_authorizes_activates_and_lists_events(self):
        status, created = self.request(
            "POST",
            "/v1/campaigns",
            {
                "candidate_name": "Test Candidate",
                "candidate_email": "candidate@example.com",
                "target_role": "Operations Analyst",
                "city": "Riyadh",
            },
        )
        self.assertEqual(status, 201)
        campaign_id = created["campaign"]["id"]
        token = created["campaign_access_token"]
        self.assertTrue(token)
        self.assertFalse(created["campaign"]["external_execution_enabled"])

        denied_status, denied = self.request("GET", f"/v1/campaigns/{campaign_id}")
        self.assertEqual(denied_status, 403)
        self.assertEqual(denied["error"], "forbidden")

        ok_status, summary = self.request("GET", f"/v1/campaigns/{campaign_id}", headers={"X-Campaign-Token": token})
        self.assertEqual(ok_status, 200)
        self.assertEqual(summary["campaign"]["status"], "intake_received")

        start_status, started = self.request("POST", f"/v1/campaigns/{campaign_id}/start", headers={"X-Campaign-Token": token})
        self.assertEqual(start_status, 200)
        self.assertEqual(started["campaign"]["status"], "active_readonly")
        self.assertFalse(started["campaign"]["external_execution_enabled"])

        event_status, events = self.request("GET", f"/v1/campaigns/{campaign_id}/events", headers={"X-Campaign-Token": token})
        self.assertEqual(event_status, 200)
        self.assertGreaterEqual(len(events["events"]), 2)
        self.assertIn("campaign_activated", {event["event_type"] for event in events["events"]})

    def test_campaign_api_accepts_multipart_cv_and_stores_an_isolated_artifact(self):
        status, created = self.multipart_request(
            "/v1/campaigns",
            {
                "candidate_name": "Upload Candidate",
                "candidate_email": "upload@example.com",
                "target_role": "Industrial Engineer",
            },
            "candidate-cv.pdf",
            b"%PDF-1.4 campaign upload test",
        )
        self.assertEqual(status, 201)
        campaign = db.get_campaign(created["campaign"]["id"])
        self.assertEqual(campaign["cv_original_name"], "candidate-cv.pdf")
        self.assertTrue(Path(campaign["cv_path"]).exists())
        self.assertEqual(len(campaign["cv_sha256"]), 64)

    def test_legacy_controls_require_admin_and_execution_stays_disabled(self):
        status, body = self.request("POST", "/run")
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "forbidden")
        status, body = self.request("POST", "/run", headers={"X-Admin-Token": "test-admin-token"})
        self.assertEqual(status, 202)
        self.assertFalse(body["external_execution_enabled"])

    def test_admin_contact_import_requires_token_and_never_enables_delivery(self):
        payload = {
            "verification_source": "verified-contact-export-2026-08",
            "mark_verified": True,
            "contacts": [{"email": "recruiter@example.com", "name": "Ada", "company": "BrightTech"}],
        }
        denied_status, denied = self.request("POST", "/v1/admin/contacts/import", payload)
        self.assertEqual(403, denied_status)
        self.assertEqual("forbidden", denied["error"])
        status, body = self.request(
            "POST", "/v1/admin/contacts/import", payload, headers={"X-Admin-Token": "test-admin-token"}
        )
        self.assertEqual(200, status)
        self.assertEqual(1, body["import"]["verified"])
        self.assertFalse(body["delivery_enabled"])
        self.assertEqual("recruiter@example.com", db.get_verified_outreach_contacts(campaign_id="new-campaign")[0]["email"])

    def test_safe_maintenance_recovers_stale_work_without_external_execution(self):
        campaign, _ = db.create_campaign(
            candidate_name="Test Candidate", candidate_email="candidate@example.com", target_role="Engineer"
        )
        outbox_id, added = db.queue_action(campaign["id"], "draft_only", {"reason": "test"})
        self.assertTrue(added)
        with db.connection() as c:
            c.execute("UPDATE action_outbox SET status='claimed', locked_at=0 WHERE id=?", (outbox_id,))
        result = campaign_worker.run_maintenance_cycle()
        self.assertTrue(result["ok"])
        self.assertEqual(result["external_execution"], "disabled")
        self.assertIn("greenhouse", result["configured_sources"])
        self.assertIn("ashby", result["configured_sources"])
        with db.connection() as c:
            row = c.execute("SELECT status FROM action_outbox WHERE id=?", (outbox_id,)).fetchone()
        self.assertEqual(row["status"], "pending")


if __name__ == "__main__":
    unittest.main(verbosity=2)

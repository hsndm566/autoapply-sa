from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import db
import hermes_gateway


class HermesGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "gateway.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        self.old_token = os.environ.get("HERMES_GATEWAY_TOKEN")
        os.environ["HERMES_GATEWAY_TOKEN"] = "gateway-test-token"
        self.addCleanup(self._restore_token)
        self.cv = Path(self.temp_dir.name) / "candidate-cv.pdf"
        self.cv.write_bytes(b"%PDF-1.4\nSample preview CV\n%%EOF")
        campaign, _token = db.create_campaign(
            candidate_name="Sample Candidate",
            candidate_email="candidate@example.test",
            target_role="Supply Chain Coordinator",
            cv_path=str(self.cv),
            cv_original_name=self.cv.name,
            cv_sha256="test-sha",
        )
        self.campaign_id = campaign["id"]

    def _restore_token(self) -> None:
        if self.old_token is None:
            os.environ.pop("HERMES_GATEWAY_TOKEN", None)
        else:
            os.environ["HERMES_GATEWAY_TOKEN"] = self.old_token

    def item(self) -> dict[str, object]:
        return {
            "company": "Bright Logistics",
            "role": "Supply Chain Coordinator",
            "job_url": "https://example.com/jobs/1",
            "source_url": "https://example.com/jobs/1",
            "recipient": "recruiter@example.com",
            "contact_name": "Recruiter",
            "subject": "Application — Supply Chain Coordinator — Bright Logistics",
            "draft": "Dear Bright Logistics team, I am applying for the Supply Chain Coordinator role.",
            "contact_verification": "verified_public_listing",
            "contact_email_matches_source": True,
            "language": "english",
        }

    def test_gateway_requires_token(self) -> None:
        self.assertFalse(hermes_gateway.authorized(""))
        self.assertTrue(hermes_gateway.authorized("gateway-test-token"))
        self.assertFalse(hermes_gateway.authorized("wrong-token"))

    def test_preview_does_not_queue_or_send(self) -> None:
        decision = SimpleNamespace(approved=True, status="approved", findings=[])
        with patch.object(hermes_gateway.auditor, "audit_application", return_value=decision):
            result = hermes_gateway.prepare_batch(self.campaign_id, [self.item()])
        self.assertTrue(result["ok"])
        self.assertEqual("draft_only", result["mode"])
        self.assertEqual("apply@hsndm.tech", result["sender"])
        self.assertEqual("draft_ready", result["results"][0]["status"])
        self.assertFalse(result["results"][0]["queued"])
        self.assertFalse(result["results"][0]["sent"])
        with db.connection() as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM action_outbox").fetchone()[0])

    def test_invalid_source_verification_is_blocked(self) -> None:
        item = self.item()
        item["contact_verification"] = "unknown"
        result = hermes_gateway.prepare_batch(self.campaign_id, [item])
        self.assertEqual("blocked", result["results"][0]["status"])
        self.assertFalse(result["results"][0]["sent"])


if __name__ == "__main__":
    unittest.main()

"""Offline tests for campaign email preparation behind the Auditor gate."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import auditor
import campaign_email
import db


class CampaignEmailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "campaign-email-test.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        self.cv = Path(self.temp_dir.name) / "hasan-cv.pdf"
        self.cv.write_bytes(b"%PDF-1.4\nCampaign email test CV\n%%EOF\n")
        campaign, _token = db.create_campaign(
            candidate_name="Hasan Adam", candidate_email="hasan@example.com", target_role="Operations Analyst",
            cv_path=str(self.cv), cv_original_name=self.cv.name, cv_sha256=auditor.cv_sha256(str(self.cv)),
        )
        self.campaign_id = campaign["id"]
        self.verified_contact_id, _ = db.upsert_outreach_contact(
            email="recruiter@brighttech.example", full_name="Ada Recruiter", company="BrightTech",
            role="Recruiter", status="verified", verification_source="verified-list-2026-08",
        )
        self.unverified_contact_id, _ = db.upsert_outreach_contact(
            email="unverified@brighttech.example", full_name="Unaudited Contact", company="BrightTech",
            status="unverified", verification_source="unknown",
        )

    @staticmethod
    def approved_ai(_prompt, _package):
        return {"decision": "approve", "confidence": 0.96, "reasons": ["Complete and tailored."], "required_fixes": []}

    @staticmethod
    def job() -> dict:
        return {"company": "BrightTech", "role": "Operations Analyst", "url": "https://careers.brighttech.example/jobs/operations-1"}

    @staticmethod
    def draft() -> str:
        return (
            "Dear BrightTech team, I am applying for the Operations Analyst role. "
            "My operations and process-improvement experience align with the analytical work described for BrightTech."
        )

    def test_verified_contact_and_approved_package_queue_one_email_intent(self) -> None:
        result = campaign_email.prepare_audited_campaign_email(
            self.campaign_id, self.verified_contact_id, application_id="campaign-email-001",
            job=self.job(), draft=self.draft(), ai_reviewer=self.approved_ai,
        )
        self.assertTrue(result["queued"])
        summary = db.campaign_summary(self.campaign_id)
        self.assertEqual({"pending": 1}, summary["outbox_counts"])
        self.assertEqual([], db.get_verified_outreach_contacts(campaign_id=self.campaign_id))
        events = db.list_campaign_events(self.campaign_id)
        self.assertIn("email_application_queued", {event["event_type"] for event in events})

    def test_unverified_contact_is_blocked_before_audit_or_queue(self) -> None:
        with self.assertRaises(PermissionError):
            campaign_email.prepare_audited_campaign_email(
                self.campaign_id, self.unverified_contact_id, application_id="campaign-email-002",
                job=self.job(), draft=self.draft(), ai_reviewer=self.approved_ai,
            )
        self.assertEqual({}, db.campaign_summary(self.campaign_id)["outbox_counts"])

    def test_generic_draft_is_audit_rejected_and_not_reserved(self) -> None:
        result = campaign_email.prepare_audited_campaign_email(
            self.campaign_id, self.verified_contact_id, application_id="campaign-email-003",
            job=self.job(), draft="Dear Hiring Manager, I would love to apply.", ai_reviewer=self.approved_ai,
        )
        self.assertFalse(result["queued"])
        self.assertIn("DRAFT_PLACEHOLDER", result["findings"])
        self.assertEqual({}, db.campaign_summary(self.campaign_id)["outbox_counts"])
        self.assertEqual(1, len(db.get_verified_outreach_contacts(campaign_id=self.campaign_id)))


if __name__ == "__main__":
    unittest.main(verbosity=2)

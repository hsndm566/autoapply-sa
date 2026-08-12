"""Offline tests for the fail-closed Greenhouse CV upload proof adapter."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import auditor
import db
from greenhouse_upload_proof import GreenhouseUploadProofAdapter, GreenhouseUploadRequest


class FakeGreenhouseSession:
    def __init__(self, *, required_fields: list[str] | None = None, confirmation: bool = True) -> None:
        self.required_fields = required_fields or ["first_name", "last_name", "email", "resume"]
        self.confirmation = confirmation
        self.goto_calls = 0
        self.click_calls = 0
        self.upload_path = ""
        self.values: dict[str, str] = {}
        self.url = ""

    def goto(self, url: str) -> None:
        self.goto_calls += 1
        self.url = url

    def count(self, selector: str) -> int:
        if selector == 'input[type="file"]':
            return 1
        if selector == "button[type=submit]":
            return 1
        if selector.startswith('[name="') and selector.endswith('"]'):
            return 1
        return 0

    def input_type(self, selector: str) -> str:
        return "file" if selector == 'input[type="file"]' else "text"

    def set_input_files(self, selector: str, path: str) -> None:
        self.upload_path = path

    def selected_filename(self, selector: str) -> str:
        return Path(self.upload_path).name if self.upload_path else ""

    def fill_by_name(self, name: str, value: str) -> None:
        self.values[name] = value

    def unresolved_required_fields(self) -> list[str]:
        unresolved = []
        for field in self.required_fields:
            if field == "resume" and not self.upload_path:
                unresolved.append(field)
            elif field != "resume" and not self.values.get(field):
                unresolved.append(field)
        return unresolved

    def click(self, selector: str) -> None:
        self.click_calls += 1
        self.url = "https://boards.greenhouse.io/brighttech/confirmation"

    def current_url(self) -> str:
        return self.url

    def visible_text(self) -> str:
        return "Thank you for applying. Your application has been received." if self.confirmation else "Form submitted"


class GreenhouseUploadProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "greenhouse-proof-test.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        self.cv = Path(self.temp_dir.name) / "verified-cv.pdf"
        self.cv.write_bytes(b"%PDF-1.4\nGreenhouse proof test CV\n%%EOF\n")
        campaign, _token = db.create_campaign(
            candidate_name="Hasan Adam",
            candidate_email="hasan@example.com",
            target_role="Business Systems Analyst",
            cv_path=str(self.cv),
            cv_original_name=self.cv.name,
            cv_sha256=auditor.cv_sha256(str(self.cv)),
        )
        self.campaign_id = campaign["id"]

    @staticmethod
    def approved_ai(_prompt, _package):
        return {"decision": "approve", "confidence": 0.95, "reasons": ["Complete and tailored."], "required_fixes": []}

    def package(self) -> dict:
        return {
            "application_id": "greenhouse-proof-app-001",
            "job": {
                "company": "BrightTech",
                "role": "Business Systems Analyst",
                "url": "https://boards.greenhouse.io/brighttech/jobs/123456",
            },
            "candidate": {
                "full_name": "Hasan Adam",
                "email": "hasan@example.com",
                "cv_path": str(self.cv),
                "cv_text": "Industrial engineering graduate with business systems experience.",
            },
            "draft": (
                "Dear BrightTech team, I am applying for the Business Systems Analyst role. "
                "My business systems and process-improvement experience align with the operational work described in the posting."
            ),
            "destination": {"recipient": "", "subject": "", "is_test_recipient": False},
            "submission": {
                "channel": "portal",
                "mode": "live",
                "cv_transport": "portal_file_upload_verified",
                "source": "greenhouse",
            },
        }

    def request(self, package: dict, token: str) -> GreenhouseUploadRequest:
        return GreenhouseUploadRequest(
            campaign_id=self.campaign_id,
            campaign_job_id="",
            application_id=package["application_id"],
            application_package=package,
            auditor_approval_token=token,
            job_url=package["job"]["url"],
            cv_path=str(self.cv),
            form_values={"first_name": "Hasan", "last_name": "Adam", "email": "hasan@example.com"},
            submit_selector="button[type=submit]",
        )

    def test_default_configuration_blocks_before_opening_a_browser(self) -> None:
        package = self.package()
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        session = FakeGreenhouseSession()
        result = GreenhouseUploadProofAdapter(session).prove(self.request(package, decision.approval_token))
        self.assertEqual("blocked", result.status)
        self.assertEqual("GREENHOUSE_LIVE_SUBMISSION_DISABLED", result.reason)
        self.assertEqual(0, session.goto_calls)
        self.assertEqual(0, session.click_calls)

    def test_confirmed_submission_records_non_sensitive_evidence(self) -> None:
        package = self.package()
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        session = FakeGreenhouseSession()
        result = GreenhouseUploadProofAdapter(session, live_submission_enabled=True).prove(self.request(package, decision.approval_token))
        self.assertTrue(result.submitted_confirmed, result.reason)
        self.assertEqual(self.cv.name, result.selected_filename)
        self.assertTrue(result.cv_sha256)
        self.assertTrue(result.confirmation_digest)
        self.assertEqual(1, session.click_calls)
        self.assertNotIn(str(self.cv), str(result.as_evidence()))
        summary = db.campaign_summary(self.campaign_id)
        self.assertEqual(1, summary["evidence_count"])
        events = db.list_campaign_events(self.campaign_id)
        self.assertIn("portal_submission_confirmed", {item["event_type"] for item in events})

    def test_unmapped_required_field_stops_after_cv_selection_without_submit(self) -> None:
        package = self.package()
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        session = FakeGreenhouseSession(required_fields=["first_name", "last_name", "email", "resume", "work_authorization"])
        result = GreenhouseUploadProofAdapter(session, live_submission_enabled=True).prove(self.request(package, decision.approval_token))
        self.assertEqual("upload_selected", result.status)
        self.assertEqual("UNMAPPED_REQUIRED_FIELDS", result.reason)
        self.assertEqual(["work_authorization"], result.evidence["unresolved_fields"])
        self.assertEqual(0, session.click_calls)

    def test_missing_auditor_approval_blocks_before_opening_a_browser(self) -> None:
        package = self.package()
        session = FakeGreenhouseSession()
        result = GreenhouseUploadProofAdapter(session, live_submission_enabled=True).prove(self.request(package, "missing-token"))
        self.assertEqual("blocked", result.status)
        self.assertTrue(result.reason.startswith("AUDITOR_RECHECK_FAILED"))
        self.assertEqual(0, session.goto_calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)

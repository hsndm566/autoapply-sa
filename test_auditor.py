#!/usr/bin/env python3
"""Offline regression tests for the mandatory Auditor gate."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import auditor
import db


class AuditorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "audit-test.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        self.cv = Path(self.temp_dir.name) / "hasan-adam-cv.pdf"
        self.cv.write_bytes(b"%PDF-1.4\nAutoApply test CV\n%%EOF\n")

    def package(self, *, channel="email", transport="email_attachment", draft=None):
        return {
            "application_id": "app-test-001",
            "job": {
                "company": "BrightTech",
                "role": "Business Systems Analyst",
                "url": "https://boards.greenhouse.io/brighttech/jobs/123456",
            },
            "candidate": {
                "full_name": "Hasan Adam",
                "email": "hasan@example.com",
                "cv_path": str(self.cv),
                "cv_text": "Industrial Engineering graduate with process-improvement experience.",
            },
            "draft": draft or (
                "Dear BrightTech team, I am applying for the Business Systems Analyst role. "
                "My process-improvement experience and analytical background align with the operational work described in your posting."
            ),
            "destination": {
                "recipient": "careers@brighttech.example" if channel == "email" else "",
                "subject": "Application — Business Systems Analyst",
                "is_test_recipient": False,
            },
            "submission": {"channel": channel, "mode": "live", "cv_transport": transport},
        }

    @staticmethod
    def approved_ai(_prompt, _package):
        return {"decision": "approve", "confidence": 0.95, "reasons": ["Complete and tailored."], "required_fixes": []}

    def test_valid_email_package_is_approved_and_attached(self):
        package = self.package()
        decision = auditor.audit_application("app-test-001", package, ai_reviewer=self.approved_ai)
        self.assertTrue(decision.approved, decision.summary)
        auditor.assert_execution_allowed("app-test-001", package, decision.approval_token)
        message = auditor.build_approved_email(package, "hasan@example.com", decision.approval_token)
        attachments = list(message.iter_attachments())
        self.assertEqual(1, len(attachments))
        self.assertEqual(self.cv.name, attachments[0].get_filename())

    def test_missing_cv_rejects_before_ai_review(self):
        package = self.package()
        package["candidate"]["cv_path"] = str(Path(self.temp_dir.name) / "missing.pdf")
        decision = auditor.audit_application("app-test-001", package, ai_reviewer=self.approved_ai)
        self.assertFalse(decision.approved)
        self.assertIn("CV_NOT_FOUND", {finding.code for finding in decision.findings})

    def test_generic_or_mismatched_draft_is_rejected(self):
        package = self.package(draft="Dear Hiring Manager, I am interested in this opportunity and would love to talk.")
        decision = auditor.audit_application("app-test-001", package, ai_reviewer=self.approved_ai)
        self.assertFalse(decision.approved)
        codes = {finding.code for finding in decision.findings}
        self.assertIn("DRAFT_PLACEHOLDER", codes)
        self.assertIn("COMPANY_NOT_PERSONALIZED", codes)

    def test_portal_without_verified_file_upload_is_rejected(self):
        package = self.package(channel="portal", transport="portal_text_fields_only")
        decision = auditor.audit_application("app-test-001", package, ai_reviewer=self.approved_ai)
        self.assertFalse(decision.approved)
        self.assertIn("PORTAL_CV_UPLOAD_UNVERIFIED", {finding.code for finding in decision.findings})

    def test_unavailable_ai_reviewer_fails_closed(self):
        package = self.package()
        decision = auditor.audit_application("app-test-001", package, ai_reviewer=None, require_ai_review=True)
        self.assertFalse(decision.approved)
        self.assertIn("AI_REVIEW_REQUIRED", {finding.code for finding in decision.findings})

    def test_tampered_package_invalidates_approval(self):
        package = self.package()
        decision = auditor.audit_application("app-test-001", package, ai_reviewer=self.approved_ai)
        self.assertTrue(decision.approved, decision.summary)
        package["destination"]["recipient"] = "different-company@example.com"
        with self.assertRaises(PermissionError):
            auditor.assert_execution_allowed("app-test-001", package, decision.approval_token)


if __name__ == "__main__":
    unittest.main(verbosity=2)

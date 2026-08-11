#!/usr/bin/env python3
"""Safe local smoke test for the Auditor pipeline.

This test simulates a complete application package through the approval and
email-construction boundary. It never imports a browser submitter, never opens
SMTP, never contacts an LLM provider, and never contacts a job board.

Run: python3 smoke_test_audited_pipeline.py
Expected: one approved email package with a real CV attachment, followed by one
rejected portal package because verified CV file upload is not implemented yet.
"""
from __future__ import annotations

import os
import tempfile
from copy import deepcopy
from pathlib import Path

import auditor
import db


def independent_reviewer(_system_prompt, _package):
    """Deterministic stand-in for Agent 2's independent model during local tests."""
    return {
        "decision": "approve",
        "confidence": 0.99,
        "reasons": ["Company, role, CV artifact, and destination are present."],
        "required_fixes": [],
    }


def build_package(cv_path: Path):
    return {
        "application_id": "local-e2e-demo-001",
        "job": {
            "company": "BrightTech",
            "role": "Business Systems Analyst",
            "url": "https://boards.greenhouse.io/brighttech/jobs/123456",
        },
        "candidate": {
            "full_name": "Hasan Adam",
            "email": "hasan@example.com",
            "cv_path": str(cv_path),
            "cv_text": "Industrial Engineering graduate with process-improvement experience.",
        },
        "draft": (
            "Dear BrightTech team, I am applying for the Business Systems Analyst role. "
            "My process-improvement experience and analytical background align with the "
            "operational work described in your job posting."
        ),
        "destination": {
            "recipient": "careers@brighttech.example",
            "subject": "Application — Business Systems Analyst",
            "is_test_recipient": False,
        },
        "submission": {
            "channel": "email",
            "mode": "live",
            "cv_transport": "email_attachment",
        },
    }


def main():
    with tempfile.TemporaryDirectory(prefix="autoapply-auditor-") as workdir:
        original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(workdir, "audit-test.db")
        try:
            cv_path = Path(workdir) / "candidate-cv.pdf"
            cv_path.write_bytes(b"%PDF-1.4\nSafe local smoke-test CV\n%%EOF\n")
            package = build_package(cv_path)

            # Stage 1: Worker creates a package. Stage 2: Auditor approves it.
            decision = auditor.audit_application(
                package["application_id"], package, ai_reviewer=independent_reviewer, require_ai_review=True
            )
            assert decision.approved, decision.summary
            print("PASS 1: Auditor approved a complete, personalized email package.")

            # Stage 3: Dispatcher must re-check the exact approved package before
            # it can receive an email object. This constructs, but does not send,
            # a message with a CV attachment.
            message = auditor.build_approved_email(package, "hasan@example.com", decision.approval_token)
            attachment = next(message.iter_attachments(), None)
            assert attachment is not None and attachment.get_filename() == cv_path.name
            print("PASS 2: Dispatcher received an approved email with a real CV attachment.")
            print("SAFE: No SMTP connection was opened and no email was sent.")

            # Stage 4: The same application through the current portal path must
            # stop because no verified browser file upload exists yet.
            portal_package = deepcopy(package)
            portal_package["application_id"] = "local-e2e-demo-portal-001"
            portal_package["destination"] = {"kind": "job_portal", "url": package["job"]["url"], "is_test_recipient": False}
            portal_package["submission"] = {
                "channel": "portal",
                "mode": "live",
                "cv_transport": "portal_text_fields_only",
            }
            blocked = auditor.audit_application(
                portal_package["application_id"], portal_package, ai_reviewer=independent_reviewer, require_ai_review=True
            )
            assert not blocked.approved
            codes = {finding.code for finding in blocked.findings}
            assert "PORTAL_CV_UPLOAD_UNVERIFIED" in codes
            print("PASS 3: Auditor blocked portal execution without verified CV upload.")
            print("\nRESULT: The Auditor pipeline is working locally and no external side effect occurred.")
        finally:
            db.DB_PATH = original_db_path


if __name__ == "__main__":
    main()

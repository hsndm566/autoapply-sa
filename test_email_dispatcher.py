"""Offline tests for human + Auditor gated durable application dispatch."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auditor
import db
import email_dispatcher
from draft_review import approve_draft
from warmup_config import SCHEDULED_DELIVERY_ENVIRONMENT_FLAG, SCHEDULED_DELIVERY_SCOPE, WARMUP_ENVIRONMENT_FLAG, WARMUP_EVIDENCE_TYPE, WARMUP_SCOPE


class EmailDispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "email-dispatch-test.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        self.env_keys = ("EMAIL_OUTREACH_ENABLED", "GMAIL_USER", "GMAIL_APP_PASSWORD", "BREVO_API_KEY", WARMUP_ENVIRONMENT_FLAG, SCHEDULED_DELIVERY_ENVIRONMENT_FLAG)
        self.old_env = {key: os.environ.get(key) for key in self.env_keys}
        self.addCleanup(self._restore_env)
        for key in self.env_keys:
            os.environ.pop(key, None)
        self.cv = Path(self.temp_dir.name) / "hasan-cv.pdf"
        self.cv.write_bytes(b"%PDF-1.4\nEmail dispatcher test CV\n%%EOF\n")
        campaign, _token = db.create_campaign(
            candidate_name="Hasan Adam",
            candidate_email="hasan@example.com",
            target_role="Operations Analyst",
            cv_path=str(self.cv),
            cv_original_name=self.cv.name,
            cv_sha256=auditor.cv_sha256(str(self.cv)),
        )
        self.campaign_id = campaign["id"]

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @staticmethod
    def approved_ai(_prompt, _package):
        return {"decision": "approve", "confidence": 0.95, "reasons": ["Complete and tailored."], "required_fixes": []}

    def package(self) -> dict:
        return {
            "application_id": "email-app-001",
            "job": {"company": "BrightTech", "role": "Operations Analyst", "url": "https://careers.brighttech.example/jobs/1"},
            "candidate": {
                "full_name": "Hasan Adam", "email": "hasan@example.com", "cv_path": str(self.cv),
                "cv_text": "Operations analyst with process-improvement experience.",
            },
            "draft": (
                "Dear BrightTech team, I am applying for the Operations Analyst role. "
                "My process-improvement experience and operational analysis background align with your team’s needs."
            ),
            "destination": {"recipient": "recruiting@brighttech.example", "subject": "Application — Operations Analyst", "is_test_recipient": False},
            "submission": {"channel": "email", "mode": "live", "cv_transport": "email_attachment"},
        }

    def human_approval(self, package: dict) -> dict:
        job = dict(package.get("job") or {})
        destination = dict(package.get("destination") or {})
        rec = {
            "source": "email",
            "posting_id": str(package.get("application_id") or "test-email"),
            "company": str(job.get("company") or ""),
            "title": str(job.get("role") or job.get("title") or ""),
            "job_url": str(job.get("url") or ""),
            "_campaign_id": self.campaign_id,
            "_path": "direct_email",
            "_state": "drafted",
            "_draft": {
                "cover_letter": str(package.get("draft") or ""),
                "subject": str(destination.get("subject") or ""),
                "flagged_claims": [],
                "approved_by": None,
                "approved_at": None,
                "approval_digest": None,
            },
        }
        return approve_draft(rec, approved_by="test-human")

    def queue_valid_action(self) -> str:
        package = self.package()
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        self.assertTrue(decision.approved, decision.summary)
        action_id, added = email_dispatcher.queue_audited_email_application(
            self.campaign_id,
            package,
            decision.approval_token,
            human_approval_record=self.human_approval(package),
        )
        self.assertTrue(added)
        return action_id

    def action_status(self, action_id: str) -> str:
        with db.connection() as c:
            return str(c.execute("SELECT status FROM action_outbox WHERE id=?", (action_id,)).fetchone()["status"])

    def test_disabled_dispatcher_does_not_claim_or_block_queued_actions(self) -> None:
        action_id = self.queue_valid_action()
        result = email_dispatcher.dispatch_pending()
        self.assertFalse(result["enabled"])
        self.assertEqual(0, result["claimed"])
        self.assertEqual("pending", self.action_status(action_id))

    def test_enabled_dispatcher_sends_audited_cv_attachment_and_records_evidence(self) -> None:
        action_id = self.queue_valid_action()
        os.environ["EMAIL_OUTREACH_ENABLED"] = "true"
        os.environ["GMAIL_USER"] = email_dispatcher.REQUIRED_APPLICATION_SENDER
        os.environ["GMAIL_APP_PASSWORD"] = "app-password"
        sent: list[object] = []

        def fake_send(message, sender, password):
            sent.append((message, sender, password))
            self.assertEqual(email_dispatcher.REQUIRED_APPLICATION_SENDER, sender)
            self.assertEqual("app-password", password)
            attachments = list(message.iter_attachments())
            self.assertEqual(1, len(attachments))
            self.assertEqual(self.cv.name, attachments[0].get_filename())
            self.assertEqual("application/pdf", attachments[0].get_content_type())
            self.assertEqual(self.cv.read_bytes(), attachments[0].get_payload(decode=True))
            return "smtp-message-accepted-001"

        result = email_dispatcher.dispatch_pending(send_fn=fake_send)
        self.assertEqual(1, result["claimed"])
        self.assertEqual("accepted", result["results"][0]["status"])
        self.assertEqual(1, len(sent))
        self.assertEqual("completed", self.action_status(action_id))
        summary = db.campaign_summary(self.campaign_id)
        self.assertEqual(1, summary["evidence_count"])
        self.assertIn("email_delivery_accepted", {item["event_type"] for item in db.list_campaign_events(self.campaign_id)})

    def test_explicitly_gated_verified_contact_warmup_uses_brevo_with_exact_pdf(self) -> None:
        package = self.package()
        package.update({
            "application_id": "warmup-brevo-001",
            "job": {"company": "BrightTech", "role": "Operations Analyst", "url": "", "evidence_type": WARMUP_EVIDENCE_TYPE},
            "candidate": {"full_name": "Saif Ahmed Al Nimr", "email": "apply1@hsndm.tech", "cv_path": str(self.cv)},
            "submission": {
                "channel": "email", "mode": "live", "cv_transport": "email_attachment",
                "client_id": 2, "sender_email": "apply1@hsndm.tech",
                "evidence_type": WARMUP_EVIDENCE_TYPE, "warmup_scope": WARMUP_SCOPE,
            },
        })
        decision = auditor.audit_application(package["application_id"], package, require_ai_review=False)
        self.assertTrue(decision.approved, decision.summary)
        action_id, added = email_dispatcher.queue_audited_email_application(
            self.campaign_id,
            package,
            decision.approval_token,
            human_approval_record=self.human_approval(package),
        )
        self.assertTrue(added)
        os.environ["EMAIL_OUTREACH_ENABLED"] = "true"
        os.environ[WARMUP_ENVIRONMENT_FLAG] = "true"
        os.environ["BREVO_API_KEY"] = "test-brevo-key"
        sent: list[object] = []

        def fake_brevo(message, sender, key):
            sent.append((message, sender, key))
            self.assertEqual("apply1@hsndm.tech", sender)
            self.assertEqual("test-brevo-key", key)
            attachments = list(message.iter_attachments())
            self.assertEqual(1, len(attachments))
            self.assertEqual("application/pdf", attachments[0].get_content_type())
            self.assertEqual(self.cv.read_bytes(), attachments[0].get_payload(decode=True))
            return "brevo-message-accepted-001"

        result = email_dispatcher.dispatch_pending(brevo_send_fn=fake_brevo)
        self.assertEqual(1, result["claimed"])
        self.assertEqual("accepted", result["results"][0]["status"])
        self.assertEqual("brevo", result["results"][0]["transport"])
        self.assertEqual(1, len(sent))
        self.assertEqual("completed", self.action_status(action_id))

    def test_scheduled_scope_requires_the_scheduled_environment_gate(self) -> None:
        package = self.package()
        package.update({
            "application_id": "scheduled-brevo-001",
            "job": {"company": "BrightTech", "role": "Operations Analyst", "url": "", "evidence_type": WARMUP_EVIDENCE_TYPE},
            "candidate": {"full_name": "Saif Ahmed Al Nimr", "email": "apply1@hsndm.tech", "cv_path": str(self.cv)},
            "submission": {
                "channel": "email", "mode": "live", "cv_transport": "email_attachment",
                "client_id": 2, "sender_email": "apply1@hsndm.tech",
                "evidence_type": WARMUP_EVIDENCE_TYPE, "warmup_scope": SCHEDULED_DELIVERY_SCOPE,
            },
        })
        self.assertEqual("", email_dispatcher._authorized_brevo_sender(package))
        os.environ[SCHEDULED_DELIVERY_ENVIRONMENT_FLAG] = "true"
        self.assertEqual("apply1@hsndm.tech", email_dispatcher._authorized_brevo_sender(package))

    def test_personal_sender_is_blocked_before_transport(self) -> None:
        action_id = self.queue_valid_action()
        os.environ["EMAIL_OUTREACH_ENABLED"] = "true"
        os.environ["GMAIL_USER"] = "hasanadam506@gmail.com"
        os.environ["GMAIL_APP_PASSWORD"] = "app-password"
        sent: list[object] = []

        def fake_send(message, _sender, _password):
            sent.append(message)
            return "should-not-be-called"

        result = email_dispatcher.dispatch_pending(send_fn=fake_send)
        self.assertEqual("blocked", result["results"][0]["status"])
        self.assertEqual("SENDER_NOT_ALLOWED", result["results"][0]["reason"])
        self.assertEqual([], sent)
        self.assertEqual("blocked", self.action_status(action_id))

    def test_dispatch_blocks_if_final_mime_message_lacks_pdf(self) -> None:
        action_id = self.queue_valid_action()
        os.environ["EMAIL_OUTREACH_ENABLED"] = "true"
        os.environ["GMAIL_USER"] = email_dispatcher.REQUIRED_APPLICATION_SENDER
        os.environ["GMAIL_APP_PASSWORD"] = "app-password"
        sent: list[object] = []

        message_without_attachment = email_dispatcher.EmailMessage()
        message_without_attachment["From"] = email_dispatcher.REQUIRED_APPLICATION_SENDER
        message_without_attachment["To"] = "recruiting@brighttech.example"
        message_without_attachment["Subject"] = "Application"
        message_without_attachment.set_content("Draft")

        def fake_send(message, _sender, _password):
            sent.append(message)
            return "should-not-be-called"

        with patch.object(email_dispatcher.auditor, "build_approved_email", return_value=message_without_attachment):
            result = email_dispatcher.dispatch_pending(send_fn=fake_send)
        self.assertEqual("blocked", result["results"][0]["status"])
        self.assertEqual([], sent)
        self.assertEqual("blocked", self.action_status(action_id))

    def test_builder_blocks_incomplete_pdf_even_after_structural_approval(self) -> None:
        package = self.package()
        self.cv.write_bytes(b"%PDF-1.4\\nmissing EOF")
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        self.assertTrue(decision.approved, decision.summary)
        with self.assertRaises(PermissionError):
            auditor.build_approved_email(package, "sender@example.com", decision.approval_token)

    def test_non_pdf_cv_is_rejected_before_queue(self) -> None:
        non_pdf = Path(self.temp_dir.name) / "hasan-cv.docx"
        non_pdf.write_bytes(b"PK\\x03\\x04not-a-real-docx")
        package = self.package()
        package["candidate"] = dict(package["candidate"], cv_path=str(non_pdf))
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        self.assertFalse(decision.approved)
        self.assertIn("EMAIL_CV_PDF_REQUIRED", {finding.code for finding in decision.findings})

    def test_smtp_failure_is_uncertain_and_not_retried_as_a_duplicate(self) -> None:
        action_id = self.queue_valid_action()
        os.environ["EMAIL_OUTREACH_ENABLED"] = "true"
        os.environ["GMAIL_USER"] = email_dispatcher.REQUIRED_APPLICATION_SENDER
        os.environ["GMAIL_APP_PASSWORD"] = "app-password"

        def failing_send(_message, _sender, _password):
            raise TimeoutError("SMTP timed out")

        result = email_dispatcher.dispatch_pending(send_fn=failing_send)
        self.assertEqual("uncertain", result["results"][0]["status"])
        self.assertEqual("uncertain", self.action_status(action_id))
        self.assertEqual(0, db.campaign_summary(self.campaign_id)["evidence_count"])
        self.assertIn("email_delivery_uncertain", {item["event_type"] for item in db.list_campaign_events(self.campaign_id)})

    def test_queue_rejects_a_package_without_current_auditor_approval(self) -> None:
        with self.assertRaises(PermissionError):
            email_dispatcher.queue_audited_email_application(
                self.campaign_id,
                self.package(),
                "not-an-approval",
                human_approval_record=self.human_approval(self.package()),
            )

    def test_queue_rejects_human_approval_for_different_content(self) -> None:
        package = self.package()
        decision = auditor.audit_application(package["application_id"], package, ai_reviewer=self.approved_ai)
        approval = self.human_approval(package)
        changed = dict(package, draft="Different letter after human approval")
        with self.assertRaises(PermissionError):
            email_dispatcher.queue_audited_email_application(
                self.campaign_id,
                changed,
                decision.approval_token,
                human_approval_record=approval,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import db
import v2_verified_email


class V2VerifiedEmailBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original_db = db.DB_PATH
        db.DB_PATH = str(self.root / "bridge.db")
        os.environ["CV_STORAGE_DIR"] = str(self.root / "cv")
        db.initialize()

    def tearDown(self) -> None:
        db.DB_PATH = self.original_db
        os.environ.pop("CV_STORAGE_DIR", None)
        self.temp.cleanup()

    def verified_contact(self, company: str = "Example Logistics", email: str = "careers@example.com") -> str:
        contact_id, _ = db.upsert_outreach_contact(
            email=email,
            full_name="Recruiting",
            company=company,
            role="Recruiting",
            status="verified",
            verification_source="https://example.com/careers/contact",
        )
        return contact_id

    def test_exact_company_verified_contact_is_exposed(self) -> None:
        self.verified_contact()
        capability = v2_verified_email.email_capability("Example Logistics")
        self.assertTrue(capability["emailEligible"])
        self.assertEqual("careers@example.com", capability["recipientEmail"])
        self.assertEqual("https://example.com/careers/contact", capability["recipientVerificationSource"])

    def test_similar_company_name_does_not_cross_match(self) -> None:
        self.verified_contact(company="Example Logistics Holdings")
        capability = v2_verified_email.email_capability("Example Logistics")
        self.assertFalse(capability["emailEligible"])
        self.assertIsNone(capability["recipientEmail"])

    def test_unverified_or_suppressed_contact_is_never_exposed(self) -> None:
        db.upsert_outreach_contact(
            email="hr@example.com",
            company="Example Logistics",
            status="unverified",
            verification_source="unreviewed",
        )
        self.assertFalse(v2_verified_email.email_capability("Example Logistics")["emailEligible"])
        db.upsert_outreach_contact(
            email="hr@example.com",
            company="Example Logistics",
            status="suppressed",
            verification_source="suppression-list",
        )
        self.assertFalse(v2_verified_email.email_capability("Example Logistics")["emailEligible"])

    def test_dispatch_uses_existing_auditor_queue_contact_reservation_and_dispatcher(self) -> None:
        contact_id = self.verified_contact()
        contact = v2_verified_email.verified_contact_for_company("Example Logistics")
        self.assertIsNotNone(contact)
        package_seen = {}

        def queue(campaign_id, package, approval_token):
            package_seen.update(package)
            self.assertTrue(campaign_id)
            self.assertEqual("approval-token", approval_token)
            return "outbox-1", True

        def dispatch(action, *, accounting_reservation_fn, **_kwargs):
            self.assertTrue(accounting_reservation_fn(action["payload"]["application_package"]))
            return {"status": "accepted", "transport": "brevo", "transport_evidence": "<brevo-123>"}

        with (
            patch.object(
                v2_verified_email.auditor,
                "audit_application",
                return_value=SimpleNamespace(approved=True, approval_token="approval-token", summary="approved"),
            ),
            patch.object(v2_verified_email.email_dispatcher, "queue_audited_email_application", side_effect=queue),
            patch.object(
                v2_verified_email.db,
                "claim_action",
                return_value={
                    "id": "outbox-1",
                    "campaign_id": "campaign-1",
                    "payload": {"application_package": {
                        "submission": {
                            "accounting_mode": "v2_supabase",
                            "v2_application_id": "v2-app-1",
                        }
                    }},
                },
            ),
            patch.object(v2_verified_email.email_dispatcher, "dispatch_one", side_effect=dispatch),
            patch.object(v2_verified_email.db, "reserve_campaign_contact", return_value=True) as reserve,
        ):
            result = v2_verified_email.dispatch_v2_application(
                user_id="user-1",
                candidate_email="candidate@example.com",
                candidate_name="Candidate",
                job={
                    "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
                    "company": "Example Logistics",
                    "title": "Operations Engineer",
                    "location": "Jeddah",
                    "canonicalUrl": "https://jobs.example.com/ops",
                },
                contact=contact or {},
                cv_bytes=b"%PDF-1.4\nfixture\n%%EOF\n",
                cv_name="candidate.pdf",
                draft=(
                    "Hello Example Logistics team, I am applying for the Operations Engineer role in Jeddah. "
                    "My process improvement and Excel experience are included in the attached CV for your review."
                ),
                v2_application_id="v2-app-1",
                accounting_check=lambda: True,
                ai_reviewer=lambda *_args: {"decision": "approve", "confidence": 0.99, "reasons": ["ok"], "required_fixes": []},
            )

        self.assertEqual("<brevo-123>", result["transport_evidence"])
        self.assertEqual("careers@example.com", package_seen["destination"]["recipient"])
        self.assertEqual("v2_supabase", package_seen["submission"]["accounting_mode"])
        self.assertEqual("brevo", package_seen["submission"]["delivery_provider"])
        reserve.assert_called_once()
        self.assertEqual(contact_id, reserve.call_args.args[1])

    def test_non_pdf_cv_is_blocked_before_auditor_or_transport(self) -> None:
        self.verified_contact()
        contact = v2_verified_email.verified_contact_for_company("Example Logistics")
        with self.assertRaises(v2_verified_email.V2VerifiedEmailError) as error:
            v2_verified_email.dispatch_v2_application(
                user_id="user-1",
                candidate_email="candidate@example.com",
                candidate_name="Candidate",
                job={
                    "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
                    "company": "Example Logistics",
                    "title": "Operations Engineer",
                    "canonicalUrl": "https://jobs.example.com/ops",
                },
                contact=contact or {},
                cv_bytes=b"not-pdf",
                cv_name="candidate.docx",
                draft="This draft is long enough but delivery must stop before it matters because the CV is not a PDF file.",
                v2_application_id="v2-app-1",
                accounting_check=lambda: True,
            )
        self.assertEqual("email-cv-pdf-required", error.exception.reason)


if __name__ == "__main__":
    unittest.main()

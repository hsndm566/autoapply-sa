from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import v2_site


class V2CustomerFlowTests(unittest.TestCase):
    def test_recommended_jobs_exposes_email_only_from_verified_contact_bridge(self) -> None:
        rows = [{
            "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
            "canonicalUrl": "https://jobs.example.com/ops",
            "company": "Example Logistics",
            "title": "Operations Engineer",
            "location": "Jeddah, Saudi Arabia",
            "description": "Industrial engineering and operations role",
            "lastSeenAt": "2026-09-25T18:10:05Z",
            "verifiedUntil": "2026-10-02T18:10:05Z",
            "verification": "public_ats",
        }]
        capability = {"emailEligible": True}
        with (
            patch.object(v2_site, "_request_json", return_value=rows),
            patch.object(v2_site.v2_verified_email, "email_capability", return_value=capability),
        ):
            jobs = v2_site.recommended_jobs("token", role="Industrial Engineer", city="Jeddah")
        self.assertEqual(1, len(jobs))
        self.assertEqual("Example Logistics", jobs[0]["companyName"])
        self.assertTrue(jobs[0]["emailEligible"])
        self.assertNotIn("recipientEmail", jobs[0])
        self.assertNotIn("recipientVerificationSource", jobs[0])
        self.assertNotIn("linkedin.com/jobs/search", str(jobs).lower())
        self.assertNotIn("bayt.com/en/saudi-arabia/jobs", str(jobs).lower())

    def test_recommended_jobs_returns_empty_instead_of_synthetic_fallback(self) -> None:
        with patch.object(v2_site, "_request_json", return_value=[]):
            jobs = v2_site.recommended_jobs("token", role="Industrial Engineer", city="Jeddah")
        self.assertEqual([], jobs)

    def test_private_cv_download_uses_authenticated_storage_endpoint_and_user_path(self) -> None:
        response = MagicMock()
        response.status_code = 200
        response.content = b"%PDF-test\n%%EOF"
        with (
            patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_ANON_KEY": "anon"}, clear=False),
            patch.object(v2_site.requests, "get", return_value=response) as get,
        ):
            payload, name = v2_site._download_cv(
                "user-jwt",
                "user-123",
                {
                    "resumeStoragePath": "user-123/abc-cv.pdf",
                    "resumeFileName": "Candidate CV.pdf",
                },
            )
        self.assertEqual(b"%PDF-test\n%%EOF", payload)
        self.assertEqual("Candidate CV.pdf", name)
        self.assertIn("/storage/v1/object/authenticated/candidate-cvs/user-123/abc-cv.pdf", get.call_args.args[0])
        self.assertEqual("Bearer user-jwt", get.call_args.kwargs["headers"]["Authorization"])

    def test_private_cv_download_rejects_cross_user_path_before_network(self) -> None:
        with patch.object(v2_site.requests, "get") as get:
            with self.assertRaises(v2_site.V2Error) as error:
                v2_site._download_cv(
                    "token",
                    "user-a",
                    {"resumeStoragePath": "user-b/cv.pdf", "resumeFileName": "cv.pdf"},
                )
        self.assertEqual("cv-ownership-mismatch", error.exception.reason)
        get.assert_not_called()

    def test_retry_reuses_failed_application_but_blocks_already_sent_duplicate(self) -> None:
        failed = {"id": "app-1", "status": "queued", "deliveryStatus": "blocked", "providerMessageId": None}
        with (
            patch.object(v2_site, "_existing_application", return_value=failed),
            patch.object(v2_site, "_request_json", return_value=[{**failed, "deliveryStatus": "unknown"}]) as request,
        ):
            row = v2_site._reserve_application(
                "token", "user-1",
                {
                    "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
                    "canonicalUrl": "https://jobs.example.com/ops",
                    "company": "Example",
                    "title": "Operations Engineer",
                    "location": "Jeddah",
                    "verification": "public_ats",
                },
                "hr@example.com",
                "user-1/cv.pdf",
            )
        self.assertEqual("app-1", row["id"])
        self.assertEqual("PATCH", request.call_args.args[0])

        with patch.object(v2_site, "_existing_application", return_value={**failed, "status": "applied", "providerMessageId": "<m>"}):
            with self.assertRaises(v2_site.V2Error) as error:
                v2_site._reserve_application(
                    "token", "user-1",
                    {
                        "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
                        "canonicalUrl": "https://jobs.example.com/ops",
                        "company": "Example",
                        "title": "Operations Engineer",
                    },
                    "hr@example.com",
                    "user-1/cv.pdf",
                )
        self.assertEqual("duplicate-application", error.exception.reason)

    def test_send_application_requires_server_verified_recipient(self) -> None:
        profile = {
            "fullName": "Candidate",
            "targetRole": "Industrial Engineer",
            "targetIndustry": "Engineering",
            "experienceLevel": "Entry level",
            "resumeFileName": "cv.pdf",
            "resumeSummary": "Excel, process improvement",
            "resumeStoragePath": "user-1/cv.pdf",
        }
        job = {
            "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
            "canonicalUrl": "https://jobs.example.com/ops",
            "company": "Example Logistics",
            "title": "Operations Engineer",
            "location": "Jeddah",
            "verification": "public_ats",
        }
        with (
            patch.object(v2_site, "_profile", return_value=profile),
            patch.object(v2_site, "_job", return_value=job),
            patch.object(v2_site.v2_verified_email, "verified_contact_for_company", return_value=None),
        ):
            with self.assertRaises(v2_site.V2Error) as error:
                v2_site.send_application(
                    "token",
                    {"id": "user-1", "email": "candidate@example.com"},
                    job_id=job["id"],
                )
        self.assertEqual("verified-recipient-required", error.exception.reason)

    def test_send_application_reconciles_audited_provider_evidence(self) -> None:
        profile = {
            "fullName": "Candidate",
            "targetRole": "Industrial Engineer",
            "targetIndustry": "Engineering",
            "experienceLevel": "Entry level",
            "resumeFileName": "cv.pdf",
            "resumeSummary": "Excel, process improvement",
            "resumeStoragePath": "user-1/cv.pdf",
        }
        job = {
            "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
            "canonicalUrl": "https://jobs.example.com/ops",
            "company": "Example Logistics",
            "title": "Operations Engineer",
            "location": "Jeddah",
            "verification": "public_ats",
        }
        contact = {"id": "contact-1", "email": "careers@example.com"}
        reserved = {"id": "app-1", "status": "queued", "recipientEmail": "careers@example.com"}
        sent = {"id": "app-1", "status": "applied", "providerMessageId": "<brevo-123>"}

        def existing(*_args):
            return reserved

        with (
            patch.object(v2_site, "_profile", return_value=profile),
            patch.object(v2_site, "_job", return_value=job),
            patch.object(v2_site, "_download_cv", return_value=(b"%PDF-test\n%%EOF", "cv.pdf")),
            patch.object(v2_site, "_reserve_application", return_value=reserved),
            patch.object(v2_site, "_existing_application", side_effect=existing),
            patch.object(v2_site.v2_verified_email, "verified_contact_for_company", return_value=contact),
            patch.object(
                v2_site.v2_verified_email,
                "dispatch_v2_application",
                return_value={"status": "accepted", "transport_evidence": "<brevo-123>"},
            ) as dispatch,
            patch.object(v2_site, "_patch_application", return_value=sent) as patch_application,
        ):
            result = v2_site.send_application(
                "token",
                {"id": "user-1", "email": "candidate@example.com"},
                job_id=job["id"],
            )

        self.assertTrue(result["ok"])
        self.assertEqual("<brevo-123>", result["messageId"])
        dispatch.assert_called_once()
        self.assertEqual("careers@example.com", dispatch.call_args.kwargs["contact"]["email"])
        self.assertTrue(callable(dispatch.call_args.kwargs["accounting_check"]))
        values = patch_application.call_args.args[3]
        self.assertEqual("applied", values["status"])
        self.assertEqual("sent", values["deliveryStatus"])
        self.assertEqual("<brevo-123>", values["providerMessageId"])


if __name__ == "__main__":
    unittest.main()

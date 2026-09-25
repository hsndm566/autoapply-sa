from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import v2_site


class V2CustomerFlowTests(unittest.TestCase):
    def test_recommended_jobs_returns_only_verified_supabase_rows(self) -> None:
        rows = [
            {
                "id": "199945cc-4e96-451c-bb4f-e999f37c6873",
                "canonicalUrl": "https://jobs.example.com/ops",
                "company": "Example Logistics",
                "title": "Operations Engineer",
                "location": "Jeddah, Saudi Arabia",
                "description": "Industrial engineering and operations role",
                "lastSeenAt": "2026-09-25T18:10:05Z",
                "verifiedUntil": "2026-10-02T18:10:05Z",
                "verification": "public_ats",
            }
        ]
        with patch.object(v2_site, "_request_json", return_value=rows):
            jobs = v2_site.recommended_jobs("token", role="Industrial Engineer", city="Jeddah")
        self.assertEqual(1, len(jobs))
        self.assertEqual("Example Logistics", jobs[0]["companyName"])
        self.assertEqual("https://jobs.example.com/ops", jobs[0]["url"])
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
        url = get.call_args.args[0]
        self.assertIn("/storage/v1/object/authenticated/candidate-cvs/user-123/abc-cv.pdf", url)
        self.assertEqual("Bearer user-jwt", get.call_args.kwargs["headers"]["Authorization"])

    def test_private_cv_download_rejects_cross_user_path_before_network(self) -> None:
        with patch.object(v2_site.requests, "get") as get:
            with self.assertRaises(v2_site.V2Error) as error:
                v2_site._download_cv(
                    "token",
                    "user-a",
                    {
                        "resumeStoragePath": "user-b/cv.pdf",
                        "resumeFileName": "cv.pdf",
                    },
                )
        self.assertEqual("cv-ownership-mismatch", error.exception.reason)
        get.assert_not_called()

    def test_brevo_send_requires_provider_message_id_and_attaches_cv(self) -> None:
        response = MagicMock()
        response.status_code = 201
        response.json.return_value = {"messageId": "<brevo-123>"}
        with (
            patch.dict(os.environ, {"BREVO_API_KEY": "secret", "BREVO_SENDER_EMAIL": "apply@hsndm.tech"}, clear=False),
            patch.object(v2_site.requests, "post", return_value=response) as post,
        ):
            message_id = v2_site._send_brevo(
                to_email="hr@example.com",
                candidate_email="candidate@example.com",
                candidate_name="Candidate",
                role_title="Operations Engineer",
                message="Grounded message",
                cv_bytes=b"%PDF-test\n%%EOF",
                cv_name="cv.pdf",
                idempotency_key="application-123",
            )
        self.assertEqual("<brevo-123>", message_id)
        payload = post.call_args.kwargs["json"]
        self.assertEqual("candidate@example.com", payload["replyTo"]["email"])
        self.assertEqual("cv.pdf", payload["attachment"][0]["name"])
        self.assertTrue(payload["attachment"][0]["content"])
        self.assertEqual("application-123", post.call_args.kwargs["headers"]["idempotency-key"])

    def test_brevo_2xx_without_message_id_fails_closed(self) -> None:
        response = MagicMock()
        response.status_code = 201
        response.json.return_value = {}
        with (
            patch.dict(os.environ, {"BREVO_API_KEY": "secret"}, clear=False),
            patch.object(v2_site.requests, "post", return_value=response),
        ):
            with self.assertRaises(v2_site.V2Error) as error:
                v2_site._send_brevo(
                    to_email="hr@example.com",
                    candidate_email="candidate@example.com",
                    candidate_name="Candidate",
                    role_title="Operations Engineer",
                    message="Grounded message",
                    cv_bytes=b"%PDF-test\n%%EOF",
                    cv_name="cv.pdf",
                    idempotency_key="application-123",
                )
        self.assertEqual("brevo-missing-message-id", error.exception.reason)

    def test_retry_reuses_failed_application_but_blocks_already_sent_duplicate(self) -> None:
        failed = {"id": "app-1", "status": "queued", "deliveryStatus": "blocked", "providerMessageId": None}
        with (
            patch.object(v2_site, "_existing_application", return_value=failed),
            patch.object(v2_site, "_request_json", return_value=[{**failed, "deliveryStatus": "unknown"}]) as request,
        ):
            row = v2_site._reserve_application(
                "token",
                "user-1",
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
                    "token",
                    "user-1",
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

    def test_send_application_reconciles_provider_evidence_into_same_record(self) -> None:
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
        reserved = {"id": "app-1", "status": "queued"}
        sent = {"id": "app-1", "status": "applied", "providerMessageId": "<brevo-123>"}
        with (
            patch.object(v2_site, "_profile", return_value=profile),
            patch.object(v2_site, "_job", return_value=job),
            patch.object(v2_site, "_download_cv", return_value=(b"%PDF-test\n%%EOF", "cv.pdf")),
            patch.object(v2_site, "_reserve_application", return_value=reserved),
            patch.object(v2_site, "_send_brevo", return_value="<brevo-123>"),
            patch.object(v2_site, "_patch_application", return_value=sent) as patch_application,
        ):
            result = v2_site.send_application(
                "token",
                {"id": "user-1", "email": "candidate@example.com"},
                to_email="hr@example.com",
                job_id="199945cc-4e96-451c-bb4f-e999f37c6873",
            )
        self.assertTrue(result["ok"])
        self.assertEqual("<brevo-123>", result["messageId"])
        self.assertEqual("<brevo-123>", result["application"]["providerMessageId"])
        values = patch_application.call_args.args[3]
        self.assertEqual("applied", values["status"])
        self.assertEqual("sent", values["deliveryStatus"])
        self.assertEqual("<brevo-123>", values["providerMessageId"])


if __name__ == "__main__":
    unittest.main()

"""Offline tests for optional API-gateway email personalization."""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import email_personalization
import run_scheduled_delivery as scheduled


class FakeResponse:
    def __init__(self, payload: object, *, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self) -> object:
        return self.payload


class FakeAsyncClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.post = AsyncMock(return_value=response)


class EmailPersonalizationTests(unittest.TestCase):
    def test_successful_personalization_posts_tailor_request_and_returns_email_body(self) -> None:
        client = FakeAsyncClient(FakeResponse({"status": "ok", "summary": "My verified engineering experience aligns with the stated requirements."}))

        body = asyncio.run(email_personalization.personalize_email_body(
            candidate_profile={"full_name": "Test Candidate", "skills": ["Industrial engineering"]},
            company="Test Company",
            role="Industrial Engineer",
            city="Riyadh",
            client=client,
        ))

        self.assertIsNotNone(body)
        self.assertIn("Test Company", body or "")
        self.assertIn("Industrial Engineer", body or "")
        self.assertIn("reply STOP", body or "")
        client.post.assert_awaited_once()
        _, kwargs = client.post.call_args
        self.assertEqual(email_personalization.TAILOR_ENDPOINT, client.post.call_args.args[0])
        self.assertEqual("Test Candidate", kwargs["json"]["structured_profile_json"]["full_name"])

    def test_gateway_error_returns_none_for_generic_fallback(self) -> None:
        client = FakeAsyncClient(FakeResponse({}, error=RuntimeError("gateway unavailable")))

        body = asyncio.run(email_personalization.personalize_email_body(
            candidate_profile={"full_name": "Test Candidate"},
            company="Test Company",
            role="Industrial Engineer",
            client=client,
        ))

        self.assertIsNone(body)
        client.post.assert_awaited_once()

    def test_feature_flag_off_disables_gateway_call(self) -> None:
        package = {"draft": "generic draft"}
        job = {"company": "Test Company", "role": "Industrial Engineer", "city": "Riyadh"}
        sender = {"client_name": "Test Candidate", "sender_email": "apply2@hsndm.tech", "cv_file": "client.pdf"}

        with (
            patch.dict(os.environ, {email_personalization.FEATURE_FLAG: "false"}, clear=False),
            patch.object(email_personalization, "personalize_email_body", new=AsyncMock()) as personalize,
        ):
            status = scheduled.apply_optional_personalization(package, job, sender)

        self.assertEqual("skipped", status)
        self.assertEqual("generic draft", package["draft"])
        personalize.assert_not_awaited()

    def test_feature_flag_on_uses_nonempty_gateway_body_before_audit(self) -> None:
        package = {"draft": "generic draft"}
        job = {"company": "Test Company", "role": "Industrial Engineer", "city": "Riyadh"}
        sender = {"client_name": "Test Candidate", "sender_email": "apply2@hsndm.tech", "cv_file": "client.pdf"}

        with (
            patch.dict(os.environ, {email_personalization.FEATURE_FLAG: "true"}, clear=False),
            patch.object(email_personalization, "personalize_email_body", new=AsyncMock(return_value="personalized draft")) as personalize,
        ):
            status = scheduled.apply_optional_personalization(package, job, sender)

        self.assertEqual("used", status)
        self.assertEqual("personalized draft", package["draft"])
        personalize.assert_awaited_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)

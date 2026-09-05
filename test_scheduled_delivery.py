"""Offline checks for scheduled delivery selection; no network calls or sends."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

import auditor
import run_scheduled_delivery as scheduled
from warmup_config import WARMUP_CLIENTS


class ScheduledDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        rows = []
        for client_id in (1, 2, 3):
            for index in range(7):
                rows.append({
                    "recipient_email": f"client{client_id}-{index}@example{client_id}.com",
                    "company": f"Company {client_id}-{index}",
                    "role": "Operations Coordinator" if client_id == 2 else "Industrial Engineer",
                    "city": "Jeddah",
                    "client_id": str(client_id),
                    "evidence_type": "verified_contact",
                    "public_job_url": "",
                })
        with (self.root / "jobs.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def client(self, client_id: int, cv_file: str) -> dict[str, str]:
        fixture = WARMUP_CLIENTS[client_id]
        return {"client_name": fixture["client_name"], "sender_email": fixture["sender_email"], "cv_file": cv_file}

    def test_glitchtip_initialization_is_disabled_without_dsn(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            scheduled._glitchtip_sdk = None
            self.assertFalse(scheduled.initialize_glitchtip())

    def test_glitchtip_initializes_with_a_configured_dsn(self) -> None:
        init = Mock()
        fake_sdk = SimpleNamespace(init=init)
        with patch.dict("os.environ", {"GLITCHTIP_DSN": "https://public@example.test/1"}, clear=True), patch.dict(sys.modules, {"sentry_sdk": fake_sdk}):
            scheduled._glitchtip_sdk = None
            self.assertTrue(scheduled.initialize_glitchtip())
        init.assert_called_once_with(dsn="https://public@example.test/1", traces_sample_rate=0.0, auto_session_tracking=False)

    def test_only_clients_two_and_three_are_selected_at_five_each(self) -> None:
        selected, skipped = scheduled.select_jobs(self.root / "jobs.csv", set())
        self.assertEqual(10, len(selected))
        self.assertEqual({2: 5, 3: 5}, {client_id: sum(1 for job in selected if job["client_id"] == client_id) for client_id in (2, 3)})
        self.assertGreaterEqual(skipped["inactive_client"], 7)
        self.assertGreaterEqual(skipped["per_identity_cap"], 4)

    def test_tracked_rows_are_not_selected(self) -> None:
        selected, skipped = scheduled.select_jobs(self.root / "jobs.csv", {"client2-0@example2.com", "client3-0@example3.com"})
        self.assertNotIn("client2-0@example2.com", {job["recipient_email"] for job in selected})
        self.assertNotIn("client3-0@example3.com", {job["recipient_email"] for job in selected})
        self.assertEqual(2, skipped["tracked"])

    def test_invalid_client_cv_excludes_the_entire_client_without_blocking_the_other_active_client(self) -> None:
        (self.root / "client2.pdf").write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
        (self.root / "client3.pdf").write_bytes(b"not a pdf")
        clients = {
            2: self.client(2, "client2.pdf"),
            3: self.client(3, "client3.pdf"),
        }

        deliverable, blocked_clients = scheduled.deliverable_active_clients(clients, self.root)
        selected, skipped = scheduled.select_jobs(self.root / "jobs.csv", set(), deliverable)

        self.assertEqual(frozenset({2}), deliverable)
        self.assertEqual(5, len(selected))
        self.assertTrue(all(job["client_id"] == 2 for job in selected))
        self.assertEqual(7, skipped["client_cv_invalid"])
        self.assertEqual(1, len(blocked_clients))
        self.assertIn("client 3", blocked_clients[0])

    def test_scheduled_package_uses_authorized_scope_and_passes_deterministic_review(self) -> None:
        cv = self.root / "client2.pdf"
        cv.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
        selected, _ = scheduled.select_jobs(self.root / "jobs.csv", set())
        client = self.client(2, cv.name)
        package = scheduled.build_package(next(job for job in selected if job["client_id"] == 2), client, self.root)
        self.assertEqual([], auditor.deterministic_review(package))

    def test_accepted_delivery_retains_tracking_when_supabase_sync_is_unavailable(self) -> None:
        tracking = self.root / "tracking.csv"
        cv = self.root / "client2.pdf"
        cv.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
        job = {
            "recipient_email": "recipient@example.test",
            "company": "Example Company",
            "role": "Industrial Engineer",
            "city": "Jeddah",
            "client_id": 2,
        }
        client = self.client(2, cv.name)
        package = scheduled.build_package(job, client, self.root)
        ready = [(
            job,
            client,
            package,
            auditor.AuditDecision(
                application_id=str(package["application_id"]),
                approved=True,
                approval_token="token",
                fingerprint="fixture",
                status="approved",
            ),
        )]

        with (
            patch.dict("os.environ", {"EMAIL_OUTREACH_ENABLED": "true", "AUTOAPPLY_SCHEDULED_DELIVERY": "true", "BREVO_API_KEY": "test"}),
            patch.object(scheduled.shared, "create_client_campaign", return_value="campaign-1"),
            patch.object(scheduled.email_dispatcher, "queue_audited_email_application", return_value=("action-1", True)),
            patch.object(scheduled.db, "claim_action", return_value={"id": "action-1"}),
            patch.object(scheduled.email_dispatcher, "dispatch_one", return_value={"status": "accepted", "transport": "brevo", "transport_evidence": "message-1"}),
            patch.object(scheduled.sender, "next_delay_seconds", return_value=0),
            patch.object(scheduled.supabase_delivery_sync, "sync_accepted_application", new=AsyncMock(return_value={"skipped": True, "reason": "not_configured"})) as synchronize,
        ):
            outcomes = scheduled.execute(ready, tracking, self.root)

        self.assertEqual("accepted", outcomes[0]["status"])
        self.assertEqual("fixture", outcomes[0]["package_hash"])
        self.assertTrue(tracking.exists())
        self.assertIn("recipient@example.test", tracking.read_text(encoding="utf-8"))
        synchronize.assert_called_once()
        self.assertEqual("fixture", synchronize.call_args.kwargs["package_hash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

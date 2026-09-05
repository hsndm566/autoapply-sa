"""Offline regression tests for the retired verified-contact warm-up boundaries."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import auditor
import run_verified_contact_warmup as warmup
from warmup_config import WARMUP_CLIENTS


class VerifiedContactWarmupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "tracking.csv").write_text("recipient_email,sent_at,sender_used,source_event\nold@example.com,x,x,x\n", encoding="utf-8")
        rows = []
        for client_id in (2, 3):
            for index in range(5):
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

    def test_exact_five_per_client_required(self) -> None:
        selected = warmup.load_selected_jobs(self.root / "jobs.csv", {"old@example.com"})
        self.assertEqual(10, len(selected))
        self.assertEqual({2, 3}, {item["client_id"] for item in selected})

    def test_tracked_recipient_blocks_preflight_selection(self) -> None:
        with self.assertRaisesRegex(ValueError, "already tracked"):
            warmup.load_selected_jobs(self.root / "jobs.csv", {"client2-0@example2.com"})

    def test_verified_contact_package_omits_public_url_but_preserves_pdf_requirements(self) -> None:
        cv = self.root / "client2.pdf"
        cv.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
        fixture = WARMUP_CLIENTS[2]
        client = {"client_name": fixture["client_name"], "sender_email": fixture["sender_email"], "cv_file": cv.name}
        job = warmup.load_selected_jobs(self.root / "jobs.csv", set())[0]
        package = warmup.build_package(job, client, self.root)
        findings = auditor.deterministic_review(package)
        self.assertEqual([], findings)

    def test_tracking_append_refuses_existing_recipient_and_preserves_outcome_type(self) -> None:
        tracking = self.root / "outcomes.csv"
        tracking.write_text("recipient_email,sent_at,sender_used,source_event\n", encoding="utf-8")
        sender = WARMUP_CLIENTS[3]["sender_email"]
        warmup.append_tracking(
            tracking,
            "transport-uncertain@example.com",
            sender,
            "warmup-transport-uncertain-suppressed:transport_failed:HTTPError",
        )
        with tracking.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(1, len(rows))
        self.assertEqual("warmup-transport-uncertain-suppressed:transport_failed:HTTPError", rows[0]["source_event"])
        with self.assertRaisesRegex(ValueError, "already tracked"):
            warmup.append_tracking(tracking, "transport-uncertain@example.com", sender, "duplicate")


if __name__ == "__main__":
    unittest.main(verbosity=2)

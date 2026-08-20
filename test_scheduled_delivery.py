"""Offline checks for scheduled delivery selection; no network calls or sends."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

import auditor
import run_scheduled_delivery as scheduled


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

    def test_scheduled_package_uses_authorized_scope_and_passes_deterministic_review(self) -> None:
        cv = self.root / "client2.pdf"
        cv.write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
        selected, _ = scheduled.select_jobs(self.root / "jobs.csv", set())
        client = {"client_name": "Saif Ahmed Al Nimr", "sender_email": "apply1@hsndm.tech", "cv_file": cv.name}
        package = scheduled.build_package(next(job for job in selected if job["client_id"] == 2), client, self.root)
        self.assertEqual([], auditor.deterministic_review(package))


if __name__ == "__main__":
    unittest.main(verbosity=2)

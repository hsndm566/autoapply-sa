"""Offline checks for the three-client sender preflight; no email is sent."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import send_applications as sender


class SenderPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cvs = self.root / "cvs"
        self.cvs.mkdir()
        for file_name in ("client1.pdf", "client2.pdf", "client3.pdf"):
            (self.cvs / file_name).write_bytes(b"%PDF-1.4\nfixture\n%%EOF\n")
        (self.root / "clients.csv").write_text(
            "sender_email,client_name,cv_file\n"
            "apply@hsndm.tech,Hasan Adam,client1.pdf\n"
            "apply1@hsndm.tech,Client Two,client2.pdf\n"
            "apply2@hsndm.tech,Client Three,client3.pdf\n",
            encoding="utf-8",
        )
        self.clients = sender.load_clients(self.root / "clients.csv")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_attachment_builder_uses_nonempty_complete_pdf(self) -> None:
        attachment = sender.brevo_attachment(self.cvs, "client1.pdf")
        self.assertEqual("CV.pdf", attachment["name"])
        self.assertTrue(attachment["content"])

    def test_cover_letter_uses_only_provided_identity_job_and_opt_out(self) -> None:
        body = sender.build_cover_letter("Hasan Adam", "Example Company", "Operations Coordinator", "Jeddah")
        self.assertIn("Hasan Adam", body)
        self.assertIn("Example Company", body)
        self.assertIn("Operations Coordinator", body)
        self.assertIn("Jeddah", body)
        self.assertIn(sender.OPTOUT_LINE, body)
        self.assertNotIn("experience", body.lower())
        self.assertNotIn("skills", body.lower())

    def test_batch_is_deterministic_deduplicated_and_warmup_bounded(self) -> None:
        jobs = [
            {"recipient_email": f"person{i}@example.com", "company": "Example", "role": "Role", "city": "", "client_id": 1}
            for i in range(7)
        ] + [
            {"recipient_email": f"two{i}@example.org", "company": "Example", "role": "Role", "city": "", "client_id": 2}
            for i in range(7)
        ] + [
            {"recipient_email": f"three{i}@example.net", "company": "Example", "role": "Role", "city": "", "client_id": 3}
            for i in range(7)
        ]
        selected = sender.select_batch(jobs, {"person0@example.com"}, self.clients, 15)
        senders = [sender.deterministic_sender(job, self.clients) for job in selected]
        self.assertNotIn("person0@example.com", {job["recipient_email"] for job in selected})
        self.assertEqual(15, len(selected))
        self.assertTrue(all(senders.count(address) <= 5 for address in sender.ALLOWED_SENDERS))

    def test_missing_company_or_role_is_preserved_but_not_selected(self) -> None:
        jobs_path = self.root / "jobs.csv"
        jobs_path.write_text(
            "recipient_email,company,role,city,client_id\n"
            "unknown@gmail.com,,Operations Coordinator,,1\n"
            "valid@yahoo.com,Example Co,Operations Coordinator,Jeddah,1\n",
            encoding="utf-8",
        )
        jobs = sender.load_jobs(jobs_path, self.clients)
        self.assertFalse(jobs[0]["eligible"])
        self.assertEqual("missing explicit company or role", jobs[0]["validation_error"])
        selected = sender.select_batch(jobs, set(), self.clients, 15)
        self.assertEqual(["valid@yahoo.com"], [job["recipient_email"] for job in selected])

    def test_empty_placeholder_pdf_is_blocked(self) -> None:
        (self.cvs / "empty.pdf").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "complete approved PDF"):
            sender.read_valid_pdf(self.cvs, "empty.pdf")

    def test_repository_supplied_client_cvs_are_valid_while_client_one_remains_blocked(self) -> None:
        repository_root = Path(__file__).resolve().parent
        repository_clients = sender.load_clients(repository_root / "clients.csv")
        self.assertEqual("Saif Ahmed Al Nimr", repository_clients[2]["client_name"])
        self.assertEqual("Amro Alkabeer", repository_clients[3]["client_name"])
        self.assertTrue(sender.read_valid_pdf(repository_root / "cvs", repository_clients[2]["cv_file"]))
        self.assertTrue(sender.read_valid_pdf(repository_root / "cvs", repository_clients[3]["cv_file"]))
        with self.assertRaisesRegex(ValueError, "complete approved PDF"):
            sender.read_valid_pdf(repository_root / "cvs", repository_clients[1]["cv_file"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

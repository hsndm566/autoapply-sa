"""Offline tests for verified outreach contact storage and CSV import."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import contact_import
import db


class ContactImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "contacts-test.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        campaign, _token = db.create_campaign(
            candidate_name="Hasan Adam", candidate_email="hasan@example.com", target_role="Operations Analyst"
        )
        self.campaign_id = campaign["id"]
        self.csv = Path(self.temp_dir.name) / "verified-contacts.csv"
        self.csv.write_text(
            "Email,Name,Company,Role,Status\n"
            "recruiter@brighttech.example,Ada Recruiter,BrightTech,Recruiter,\n"
            "optout@other.example,Opted Out,Other,Recruiter,opted_out\n"
            "invalid-email,Invalid,Other,Recruiter,\n",
            encoding="utf-8",
        )

    def test_verified_import_makes_only_eligible_contacts_available(self) -> None:
        result = contact_import.import_contacts_csv(self.csv, verification_source="verified-list-2026-08", mark_verified=True)
        self.assertEqual(3, result["rows"])
        self.assertEqual(2, result["inserted"])
        self.assertEqual(1, result["invalid"])
        self.assertEqual(1, result["verified"])
        contacts = db.get_verified_outreach_contacts(campaign_id=self.campaign_id)
        self.assertEqual(1, len(contacts))
        self.assertEqual("recruiter@brighttech.example", contacts[0]["email"])
        self.assertTrue(db.reserve_campaign_contact(self.campaign_id, contacts[0]["id"]))
        self.assertFalse(db.reserve_campaign_contact(self.campaign_id, contacts[0]["id"]))
        self.assertEqual([], db.get_verified_outreach_contacts(campaign_id=self.campaign_id))

    def test_import_defaults_to_unverified_and_is_not_selectable(self) -> None:
        result = contact_import.import_contacts_csv(self.csv, verification_source="unreviewed-import", mark_verified=False)
        self.assertEqual(0, result["verified"])
        self.assertEqual([], db.get_verified_outreach_contacts(campaign_id=self.campaign_id))

    def test_blocked_statuses_are_monotonic_across_verified_imports(self) -> None:
        for status in ("bounced", "suppressed", "opted_out"):
            email = f"{status}@example.com"
            db.upsert_outreach_contact(email=email, status=status, verification_source=f"seed-{status}")
            result = contact_import.import_contact_rows(
                [{"Email": email.upper(), "Status": ""}],
                verification_source="verified-cross-source",
                mark_verified=True,
            )
            contact = db.get_outreach_contact(db.upsert_outreach_contact(email=email)[0])
            self.assertEqual(status, contact["status"])
            self.assertEqual(0, result["verified"])
            self.assertEqual(1, result[status])

    def test_cross_source_duplicate_and_evidence_are_idempotent(self) -> None:
        rows = [{"Email": "Recruiter@Example.com", "Name": "First"}]
        contact_import.import_contact_rows(rows, verification_source="source-a", mark_verified=True)
        contact_import.import_contact_rows(rows, verification_source="source-a", mark_verified=True)
        contact_import.import_contact_rows(rows, verification_source="source-b", mark_verified=True)
        with db.connection() as connection:
            contacts = connection.execute("SELECT COUNT(*) AS count FROM outreach_contacts").fetchone()["count"]
            evidence = connection.execute("SELECT COUNT(*) AS count FROM outreach_contact_source_evidence").fetchone()["count"]
            attempts = connection.execute("SELECT COUNT(*) AS count FROM campaign_contact_attempts").fetchone()["count"]
            outbox = connection.execute("SELECT COUNT(*) AS count FROM action_outbox").fetchone()["count"]
        self.assertEqual(1, contacts)
        self.assertEqual(2, evidence)
        self.assertEqual(0, attempts)
        self.assertEqual(0, outbox)


if __name__ == "__main__":
    unittest.main(verbosity=2)

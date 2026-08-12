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


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from email_preparation import prepare_pending_batch


class EmailPreparationTests(unittest.TestCase):
    def test_preparation_is_non_sending_and_validates_cv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cv = root / "candidate.pdf"
            cv.write_bytes(b"%PDF-1.4\n" + b"x" * 2048)
            contacts = root / "contacts.csv"
            with contacts.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["lead_id", "company", "title", "location", "email", "status"])
                writer.writeheader()
                writer.writerow({"lead_id": "1", "company": "Logistics Co", "title": "Operations Coordinator", "location": "Jeddah", "email": "careers@example.com", "status": "new"})
                writer.writerow({"lead_id": "2", "company": "Bad", "title": "Other", "location": "", "email": "not-an-email", "status": "new"})
            output = root / "batch.json"
            result = prepare_pending_batch(limit=5, source=contacts, cv_path=cv, output=output)
            self.assertTrue(result["ok"])
            self.assertEqual(result["mode"], "preparation_only")
            self.assertFalse(result["submits_applications"])
            self.assertFalse(result["sends_email"])
            self.assertEqual(result["selected_count"], 1)
            saved = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(saved["cv"]["path"], str(cv))
            self.assertEqual(saved["candidates"][0]["email"], "careers@example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)

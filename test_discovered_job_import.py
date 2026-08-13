#!/usr/bin/env python3
import os
import tempfile
import unittest
from pathlib import Path

import db


class DiscoveredJobImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original = db.DB_PATH
        self.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = str(Path(self.temp.name) / "autoapply.db")
        db.initialize()

    def tearDown(self) -> None:
        db.DB_PATH = self.original
        self.temp.cleanup()

    def test_inserts_and_updates_new_job(self) -> None:
        first = {
            "title": "Barista",
            "company": "Example Coffee",
            "location": "Riyadh",
            "url": "https://www.bayt.com/en/saudi-arabia/jobs/barista-1/",
            "description": "First description",
            "easy_apply": True,
            "category": "service_and_entry",
            "status": "new",
        }
        self.assertEqual(db.import_discovered_jobs([first]), {"accepted": 1, "inserted": 1, "updated": 0, "skipped": 0})
        changed = dict(first, title="Barista / Cashier", description="Updated description")
        self.assertEqual(db.import_discovered_jobs([changed]), {"accepted": 1, "inserted": 0, "updated": 1, "skipped": 0})
        with db.connection() as conn:
            row = conn.execute("SELECT title, description, status FROM discovered_jobs").fetchone()
        self.assertEqual(row["title"], "Barista / Cashier")
        self.assertEqual(row["description"], "Updated description")
        self.assertEqual(row["status"], "new")

    def test_preserves_terminal_status(self) -> None:
        job = {"title": "Barista", "company": "Example Coffee", "location": "Riyadh", "url": "https://www.bayt.com/en/saudi-arabia/jobs/barista-1/", "status": "new"}
        db.import_discovered_jobs([job])
        with db.connection() as conn:
            conn.execute("UPDATE discovered_jobs SET status='submitted' WHERE url=?", (job["url"],))
        db.import_discovered_jobs([dict(job, title="Updated title", status="new")])
        with db.connection() as conn:
            row = conn.execute("SELECT title, status FROM discovered_jobs").fetchone()
        self.assertEqual(row["title"], "Updated title")
        self.assertEqual(row["status"], "submitted")

    def test_skips_invalid_jobs(self) -> None:
        result = db.import_discovered_jobs([{}, {"title": "No URL", "company": "Example"}])
        self.assertEqual(result, {"accepted": 0, "inserted": 0, "updated": 0, "skipped": 2})


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import diversity_queue


class DiversityQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.work.name) / "queue.db")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("""
                CREATE TABLE discovered_jobs (
                    id INTEGER PRIMARY KEY,
                    title TEXT, company TEXT, location TEXT, url TEXT UNIQUE,
                    description TEXT, easy_apply BOOLEAN, category TEXT, status TEXT
                )
            """)
            rows = [
                (1, "Barista", "SameCo", "Riyadh", "https://www.bayt.com/en/saudi-arabia/jobs/barista-1/", "new"),
                (2, "Waiter", "SameCo", "Riyadh", "https://www.bayt.com/en/saudi-arabia/jobs/waiter-2/", "new"),
                (3, "Customer Service Agent", "OtherCo", "Riyadh", "https://jobs.ashbyhq.com/other/3", "new"),
                (4, "Administrative Assistant", "ThirdCo", "Jeddah", "https://job-boards.greenhouse.io/third/jobs/4", "new"),
                (5, "Sales Associate", "FourthCo", "Dammam", "https://www.bayt.com/en/saudi-arabia/jobs/sales-5/", "new"),
                (6, "Barista", "FifthCo", "Riyadh", "https://www.bayt.com/en/saudi-arabia/jobs/barista-6/", "new"),
            ]
            connection.executemany(
                "INSERT INTO discovered_jobs(id,title,company,location,url,status) VALUES(?,?,?,?,?,?)", rows
            )
            connection.execute("""
                CREATE TABLE applications (
                    id INTEGER PRIMARY KEY, client_id TEXT, job_posting_hash TEXT,
                    company TEXT, role TEXT, status TEXT, attempt_count INTEGER,
                    last_error TEXT, created_at REAL, updated_at REAL
                )
            """)
            connection.commit()

    def tearDown(self) -> None:
        self.work.cleanup()

    def test_same_employer_only_appears_once(self) -> None:
        selected = diversity_queue.select_handoffs(self.db_path, limit=6, bayt_profile_ready=True, now=1_000_000)
        self.assertEqual(sum(1 for item in selected if item.company == "SameCo"), 1)
        self.assertTrue(all(item.handoff_state in {"browser_inspection_ready", "source_verification_required"} for item in selected))

    def test_source_rotation_and_summary_are_read_only(self) -> None:
        before = Path(self.db_path).read_bytes()
        summary = diversity_queue.queue_summary(self.db_path, limit=5, bayt_profile_ready=True)
        after = Path(self.db_path).read_bytes()
        self.assertEqual(before, after)
        self.assertFalse(summary["submits_applications"])
        self.assertLessEqual(max(summary["selected_by_source"].values()), diversity_queue.SOURCE_BUNDLE_CAP)
        self.assertIn("bayt", summary["selected_by_source"])
        self.assertIn("ashby", summary["selected_by_source"])
        self.assertIn("greenhouse", summary["selected_by_source"])

    def test_recent_submitted_employer_is_excluded(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "INSERT INTO applications(client_id,job_posting_hash,company,role,status,attempt_count,last_error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                ("hasan", "submitted-sameco", "SameCo", "Prior role", "submitted", 1, "", 1_000_000, 1_000_000),
            )
            connection.commit()
        selected = diversity_queue.select_handoffs(self.db_path, limit=5, bayt_profile_ready=True, now=1_000_001)
        self.assertFalse(any(item.company == "SameCo" for item in selected))


if __name__ == "__main__":
    unittest.main(verbosity=2)

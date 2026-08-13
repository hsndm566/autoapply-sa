#!/usr/bin/env python3
from __future__ import annotations

import importlib
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import diversity_queue


class BrowserHandoffLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp.name) / "handoff.db")
        os.environ["DB_PATH"] = self.db_path
        import db
        self.db = importlib.reload(db)
        self.db.initialize()
        self.url = "https://www.bayt.com/en/saudi-arabia/jobs/barista-ledger/"
        self.db.import_discovered_jobs([
            {"title": "Barista", "company": "Ledger Cafe", "location": "Riyadh", "url": self.url, "status": "new"},
        ])

    def tearDown(self) -> None:
        os.environ.pop("DB_PATH", None)
        self.temp.cleanup()

    def _selected_urls(self) -> set[str]:
        return {item.url for item in diversity_queue.select_handoffs(self.db_path, limit=5, bayt_profile_ready=True)}

    def test_recent_retry_is_cooled_down_then_available_once(self) -> None:
        self.db.record_browser_handoff_attempt(self.url, "transient_error", "temporary browser timeout")
        self.assertNotIn(self.url, self._selected_urls())
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE browser_handoff_attempts SET updated_at=? WHERE job_url=?",
                (time.time() - diversity_queue.RETRY_COOLDOWN_SECONDS - 1, self.url),
            )
            connection.commit()
        self.assertIn(self.url, self._selected_urls())

    def test_verified_eligibility_reopening_restores_queue_access(self) -> None:
        self.db.record_browser_handoff_attempt(self.url, "abandoned", "nationality fact was not yet established")
        self.assertNotIn(self.url, self._selected_urls())
        record = self.db.record_browser_handoff_attempt(self.url, "eligibility_reopened", "candidate directly confirmed Saudi nationality")
        self.assertEqual(record["status"], "eligibility_reopened")
        self.assertIn(self.url, self._selected_urls())

    def test_second_retry_and_captcha_are_manual_exclusions(self) -> None:
        self.db.record_browser_handoff_attempt(self.url, "form_changed", "first retry")
        self.db.record_browser_handoff_attempt(self.url, "form_changed", "second retry")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "UPDATE browser_handoff_attempts SET updated_at=? WHERE job_url=?",
                (time.time() - diversity_queue.RETRY_COOLDOWN_SECONDS - 1, self.url),
            )
            connection.commit()
        self.assertNotIn(self.url, self._selected_urls())

        other_url = "https://jobs.ashbyhq.com/example/jobs/ledger-captcha"
        self.db.import_discovered_jobs([
            {"title": "Customer Service Agent", "company": "Ledger Support", "location": "Jeddah", "url": other_url, "status": "new"},
        ])
        self.db.record_browser_handoff_attempt(other_url, "captcha", "manual attention required")
        self.assertNotIn(other_url, self._selected_urls())


if __name__ == "__main__":
    unittest.main(verbosity=2)

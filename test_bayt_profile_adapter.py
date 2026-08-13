#!/usr/bin/env python3
import os
import tempfile
import unittest
from pathlib import Path

import bayt_profile_adapter as bayt


class BaytProfileAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old = os.environ.get("BAYT_BROWSER_PROFILE_READY")
        os.environ.pop("BAYT_BROWSER_PROFILE_READY", None)

    def tearDown(self) -> None:
        if self.old is None:
            os.environ.pop("BAYT_BROWSER_PROFILE_READY", None)
        else:
            os.environ["BAYT_BROWSER_PROFILE_READY"] = self.old

    def test_rejects_non_bayt_url(self) -> None:
        result = bayt.decide(1, "https://example.com/jobs/1", current_status="new", browser_profile_ready=True)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "BAYT_URL_NOT_ALLOWED")

    def test_requires_profile_confirmation(self) -> None:
        result = bayt.decide(1, "https://www.bayt.com/en/saudi-arabia/jobs/example-1/", current_status="new")
        self.assertEqual(result.status, "waiting_for_profile")

    def test_never_reopens_recorded_submission(self) -> None:
        result = bayt.decide(118, "https://www.bayt.com/en/saudi-arabia/jobs/barista-5470679/", current_status="submitted", browser_profile_ready=True)
        self.assertEqual(result.status, "already_submitted")

    def test_profile_ready_returns_handoff_not_auto_submit(self) -> None:
        result = bayt.decide(1, "https://www.bayt.com/en/saudi-arabia/jobs/example-1/", current_status="new", browser_profile_ready=True)
        self.assertEqual(result.status, "browser_handoff_ready")
        self.assertIn("USER_BROWSER_HANDOFF", result.reason)

    def test_summary_is_read_only_and_counts_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "db.sqlite"
            import sqlite3
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE discovered_jobs (id INTEGER, url TEXT, status TEXT)")
            conn.executemany(
                "INSERT INTO discovered_jobs VALUES (?, ?, ?)",
                [
                    (1, "https://www.bayt.com/en/saudi-arabia/jobs/a-1/", "new"),
                    (2, "https://www.bayt.com/en/saudi-arabia/jobs/b-2/", "submitted"),
                ],
            )
            conn.commit()
            conn.close()
            summary = bayt.queue_summary(path)
        self.assertEqual(summary["total_bayt_leads"], 2)
        self.assertEqual(summary["submitted_leads"], [2])
        self.assertEqual(summary["by_route_status"]["waiting_for_profile"], 1)


if __name__ == "__main__":
    unittest.main()

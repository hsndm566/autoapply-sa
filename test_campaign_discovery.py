"""Offline tests for durable campaign discovery with no external execution."""
from __future__ import annotations

import os
import tempfile
import unittest

import campaign_discovery
import db
import job_schema


class CampaignDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, "campaign-discovery-test.db")
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        campaign, _token = db.create_campaign(
            candidate_name="Hasan Adam",
            candidate_email="hasan@example.com",
            target_role="Business Systems Analyst",
            city="Riyadh",
            cv_path="/tmp/does-not-matter-for-discovery.pdf",
            cv_original_name="cv.pdf",
            cv_sha256="test",
        )
        db.activate_campaign(campaign["id"])
        self.campaign = db.get_campaign(campaign["id"])

    @staticmethod
    def records() -> list[dict]:
        return [
            job_schema.normalize_job(
                source="greenhouse", employer_key="brighttech", posting_id="gh-1", company="BrightTech",
                title="Business Systems Analyst", location="Riyadh", job_url="https://boards.greenhouse.io/brighttech/jobs/1",
            ),
            job_schema.normalize_job(
                source="ashby", employer_key="secondco", posting_id="as-2", company="SecondCo",
                title="Operations Analyst", location="Remote", job_url="https://jobs.ashbyhq.com/secondco/as-2",
            ),
            job_schema.normalize_job(
                source="greenhouse", employer_key="thirdco", posting_id="gh-3", company="ThirdCo",
                title="Process Analyst", location="Jeddah", job_url="https://boards.greenhouse.io/thirdco/jobs/3",
            ),
            job_schema.normalize_job(
                source="greenhouse", employer_key="unrelated", posting_id="gh-4", company="Unrelated",
                title="Senior Designer", location="Riyadh", job_url="https://boards.greenhouse.io/unrelated/jobs/4",
            ),
        ]

    def test_discovery_persists_matching_options_without_outbox_or_execution(self) -> None:
        calls: list[tuple[list[str], bool]] = []

        def fake_discover(*, sources, fetch):
            calls.append((sources, fetch))
            return self.records()

        result = campaign_discovery.discover_campaign(self.campaign, discover_fn=fake_discover, fetch=False)
        self.assertEqual("completed", result["status"])
        self.assertEqual(["greenhouse", "ashby"], result["sources"])
        self.assertEqual(4, result["fetched"])
        self.assertEqual(3, result["matched"])
        self.assertEqual(3, result["added"])
        self.assertEqual([(["greenhouse", "ashby"], False)], calls)
        summary = db.campaign_summary(self.campaign["id"])
        self.assertEqual("active_readonly", summary["status"])
        self.assertEqual({"discovered": 3}, summary["job_counts"])
        self.assertEqual({}, summary["outbox_counts"])
        events = db.list_campaign_events(self.campaign["id"])
        self.assertIn("campaign_discovery_completed", {event["event_type"] for event in events})

    def test_percentage_caps_keep_a_nonempty_two_source_batch(self) -> None:
        records = []
        for index in range(20):
            records.append(job_schema.normalize_job(
                source="greenhouse", employer_key=f"green-{index}", posting_id=f"green-{index}",
                company=f"Green Company {index}", title="Operations Analyst", location="Remote",
                job_url=f"https://boards.greenhouse.io/green{index}/jobs/{index}",
            ))
            records.append(job_schema.normalize_job(
                source="ashby", employer_key=f"ashby-{index}", posting_id=f"ashby-{index}",
                company=f"Ashby Company {index}", title="Operations Analyst", location="Remote",
                job_url=f"https://jobs.ashbyhq.com/ashby{index}",
            ))

        result = campaign_discovery.discover_campaign(
            self.campaign, fetch=False, discover_fn=lambda *, sources, fetch: records
        )
        self.assertEqual(40, result["matched"])
        self.assertGreater(result["selected"], 0)
        self.assertGreater(result["added"], 0)
        self.assertGreater(result["source_family_cap_dropped"], 0)

    def test_cooldown_prevents_repeat_fetches_in_the_same_window(self) -> None:
        calls = 0

        def fake_discover(*, sources, fetch):
            nonlocal calls
            calls += 1
            return self.records()

        first = campaign_discovery.run_active_campaign_discovery(fetch=False, discover_fn=fake_discover)
        second = campaign_discovery.run_active_campaign_discovery(fetch=False, discover_fn=fake_discover)
        self.assertEqual(1, first["processed"])
        self.assertEqual(0, second["processed"])
        self.assertEqual(1, second["skipped_cooldown"])
        self.assertEqual(1, calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)

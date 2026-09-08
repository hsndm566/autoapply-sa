import importlib
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class ApifyCostGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.saved = {key: os.environ.get(key) for key in (
            "DB_PATH", "APIFY_API_KEY", "APIFY_PAID_ENABLED", "APIFY_COST_ESTIMATE_REVIEWED", "APIFY_COST_ESTIMATE_USD",
            "APIFY_MAX_COST_PER_RUN_USD", "APIFY_MAX_COST_DAILY_USD", "APIFY_MAX_COST_TOTAL_USD",
        )}
        for key in self.saved:
            os.environ.pop(key, None)
        os.environ["DB_PATH"] = str(Path(self.temp.name) / "guard.db")
        import db
        import apify_scraper
        self.db = importlib.reload(db)
        self.scraper = importlib.reload(apify_scraper)
        self.db.initialize()

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()
        importlib.reload(self.db)

    def _enable(self):
        os.environ.update({"APIFY_API_KEY": "unit-test-only", "APIFY_PAID_ENABLED": "true", "APIFY_COST_ESTIMATE_REVIEWED": "true",
                           "APIFY_COST_ESTIMATE_USD": "0.10", "APIFY_MAX_COST_PER_RUN_USD": "0.10",
                           "APIFY_MAX_COST_DAILY_USD": "0.20", "APIFY_MAX_COST_TOTAL_USD": "1.00"})

    def test_disabled_never_starts_actor(self):
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]), patch.object(self.scraper, "_start_actor") as start:
            self.assertEqual(self.scraper.scrape("engineer"), [])
        start.assert_not_called()

    def test_fresh_cache_precedes_free(self):
        key = self.scraper._query("Engineer", 10, "Saudi Arabia")[3]
        jobs = [{"title": "Cached", "company": "Example", "url": "https://example.test/1"}]
        self.db.put_apify_cache(key, "engineer", "saudi arabia", 10, "free", jobs)
        with patch.object(self.scraper.free_scraper, "scrape_field") as free:
            self.assertEqual(self.scraper.scrape(" engineer ", 10, "SAUDI   ARABIA"), jobs)
        free.assert_not_called()

    def test_free_result_is_persisted_and_precedes_paid(self):
        jobs = [{"title": "Free", "company": "Example", "url": "https://example.test/free"}]
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=jobs), patch.object(self.scraper, "_start_actor") as start:
            self.assertEqual(self.scraper.scrape("engineer"), jobs)
        start.assert_not_called()
        self.assertEqual(self.db.apify_usage_telemetry()["cache_entries"], 1)

    def test_budget_exhaustion_blocks_start(self):
        self._enable()
        first = self.scraper._query("first", 100, "Saudi Arabia")
        self.assertTrue(self.db.reserve_apify_run(first[3], first[0], first[1], first[2], .1, .2, 1)[0])
        second = self.scraper._query("second", 100, "Saudi Arabia")
        self.assertTrue(self.db.reserve_apify_run(second[3], second[0], second[1], second[2], .1, .2, 1)[0])
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]), patch.object(self.scraper, "_start_actor") as start:
            self.assertEqual(self.scraper.scrape("third", free_sources_exhausted=True), [])
        start.assert_not_called()

    def test_concurrent_calls_reserve_once_and_ambiguous_start_is_not_retried(self):
        self._enable()
        calls = []
        def uncertain(*_args):
            calls.append(1)
            time.sleep(.05)
            raise TimeoutError("lost response")
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]), patch.object(self.scraper, "_start_actor", side_effect=uncertain):
            threads = [threading.Thread(target=self.scraper.scrape, args=("engineer",), kwargs={"free_sources_exhausted": True}) for _ in range(2)]
            [thread.start() for thread in threads]
            [thread.join() for thread in threads]
            self.assertEqual(self.scraper.scrape("engineer", free_sources_exhausted=True), [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.db.apify_usage_telemetry()["by_status"]["uncertain"]["runs"], 1)

    def test_provider_failure_does_not_accept_partial_dataset(self):
        self._enable()
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]), patch.object(self.scraper, "_start_actor", return_value=("run-1", "dataset-1")), patch.object(self.scraper, "_run_status", return_value="FAILED"), patch.object(self.scraper, "_fetch_dataset") as fetch:
            self.assertEqual(self.scraper.scrape("engineer", free_sources_exhausted=True), [])
        fetch.assert_not_called()
        self.assertEqual(self.db.apify_usage_telemetry()["by_status"]["failed"]["runs"], 1)

    def test_empty_free_response_is_not_exhaustion_proof(self):
        self._enable()
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]), patch.object(self.scraper, "_start_actor") as start:
            self.assertEqual(self.scraper.scrape("engineer"), [])
        start.assert_not_called()

    def test_stale_cache_is_not_returned(self):
        key = self.scraper._query("engineer", 100, "Saudi Arabia")[3]
        with patch.object(self.db, "_now", return_value=time.time() - 7 * 3600):
            self.db.put_apify_cache(key, "engineer", "saudi arabia", 100, "free", [{"title": "Expired"}])
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]):
            self.assertEqual(self.scraper.scrape("engineer"), [])

    def test_query_key_separates_country_and_limit(self):
        self.assertNotEqual(self.scraper._query("engineer", 10, "Saudi Arabia")[3], self.scraper._query("engineer", 10, "UAE")[3])
        self.assertNotEqual(self.scraper._query("engineer", 10, "Saudi Arabia")[3], self.scraper._query("engineer", 20, "Saudi Arabia")[3])

    def test_success_persists_before_return(self):
        self._enable()
        items = [{"title": "Engineer", "company": "Example", "official_url": "https://example.test/job"}]
        with patch.object(self.scraper.free_scraper, "scrape_field", return_value=[]), patch.object(self.scraper, "_start_actor", return_value=("run-1", "dataset-1")), patch.object(self.scraper, "_run_status", return_value="SUCCEEDED"), patch.object(self.scraper, "_fetch_dataset", return_value=items):
            jobs = self.scraper.scrape("engineer", free_sources_exhausted=True)
        key = self.scraper._query("engineer", 100, "Saudi Arabia")[3]
        self.assertEqual(self.db.get_apify_cache(key, 3600)["jobs"], jobs)
        self.assertEqual(self.db.apify_usage_telemetry()["by_status"]["succeeded"]["runs"], 1)

    def test_large_budget_and_non_finite_estimates_fail_closed(self):
        self._enable()
        for value in ("1", "nan", "inf", "-1"):
            os.environ["APIFY_MAX_COST_PER_RUN_USD"] = value
            self.assertIsNone(self.scraper._paid_config())


if __name__ == "__main__":
    unittest.main()

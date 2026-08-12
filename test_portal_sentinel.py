"""Deterministic tests for the read-only portal Sentinel."""
from __future__ import annotations

import os
import tempfile
import unittest

import db
import portal_sentinel


BASELINE_HTML = """
<html><body><form>
  <input type='text' name='first_name' required>
  <input type='email' name='email' required>
  <input type='file' name='resume' required>
  <button type='submit'>Submit application</button>
</form></body></html>
"""
DRIFTED_HTML = """
<html><body><form>
  <input type='text' name='first_name' required>
  <input type='email' name='email' required>
  <input type='file' name='resume' required>
  <textarea name='cover_letter' required></textarea>
  <button type='submit'>Submit application</button>
</form></body></html>
"""
BLOCKED_HTML = "<html><body><form><input type='file'></form><p>Please complete the CAPTCHA to continue.</p></body></html>"


class PortalSentinelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_db_path = db.DB_PATH
        self.old_interval = os.environ.get("PORTAL_PROBE_INTERVAL_SECONDS")
        db.DB_PATH = os.path.join(self.temp_dir.name, "sentinel.db")
        os.environ["PORTAL_PROBE_INTERVAL_SECONDS"] = "21600"
        self.addCleanup(setattr, db, "DB_PATH", self.old_db_path)
        if self.old_interval is None:
            self.addCleanup(os.environ.pop, "PORTAL_PROBE_INTERVAL_SECONDS", None)
        else:
            self.addCleanup(os.environ.__setitem__, "PORTAL_PROBE_INTERVAL_SECONDS", self.old_interval)
        db.initialize()
        campaign, _token = db.create_campaign(
            candidate_name="Probe Test", candidate_email="probe@example.com", target_role="Engineer"
        )
        self.campaign_id = campaign["id"]
        db.add_campaign_job(
            self.campaign_id,
            source="greenhouse", company="Acme", title="Engineer", location="Remote",
            job_url="https://boards.greenhouse.io/acme/jobs/123", path_state="portal_complex",
        )
        self.url = "https://boards.greenhouse.io/acme/jobs/123"

    @staticmethod
    def response(body: str):
        return lambda _url, _timeout: (200, body)

    def test_baseline_then_stable_preserves_a_readonly_source_health_record(self) -> None:
        baseline = portal_sentinel.probe_source("greenhouse", self.url, fetcher=self.response(BASELINE_HTML), force=True)
        self.assertEqual("baseline", baseline.status)
        self.assertEqual(1, baseline.observation["file_input_count"])
        stable = portal_sentinel.probe_source("greenhouse", self.url, fetcher=self.response(BASELINE_HTML), force=True)
        self.assertEqual("stable", stable.status)
        self.assertEqual(baseline.fingerprint, stable.fingerprint)
        self.assertEqual("healthy", db.health_snapshot()["sources"][0]["status"])

    def test_changed_form_is_held_and_persists_previous_fingerprint(self) -> None:
        first = portal_sentinel.probe_source("greenhouse", self.url, fetcher=self.response(BASELINE_HTML), force=True)
        drift = portal_sentinel.probe_source("greenhouse", self.url, fetcher=self.response(DRIFTED_HTML), force=True)
        self.assertEqual("drifted", drift.status)
        self.assertEqual(first.fingerprint, drift.previous_fingerprint)
        self.assertEqual("PORTAL_FORM_FINGERPRINT_CHANGED", drift.error_code)
        latest = db.latest_portal_probe("greenhouse")
        self.assertEqual("drifted", latest["status"])
        self.assertEqual(4, latest["observation"]["required_control_count"])
        self.assertEqual("drifted", db.health_snapshot()["sources"][0]["status"])

    def test_captcha_is_blocked_without_any_attempt_to_interact_with_the_form(self) -> None:
        result = portal_sentinel.probe_source("greenhouse", self.url, fetcher=self.response(BLOCKED_HTML), force=True)
        self.assertEqual("blocked", result.status)
        self.assertEqual("PORTAL_BLOCKER_DETECTED", result.error_code)
        self.assertEqual(["captcha"], result.observation["blocker_markers"])

    def test_unsafe_host_is_rejected_before_fetch(self) -> None:
        called = False

        def forbidden_fetcher(_url, _timeout):
            nonlocal called
            called = True
            return 200, BASELINE_HTML

        result = portal_sentinel.probe_source("greenhouse", "https://evil.example/apply", fetcher=forbidden_fetcher)
        self.assertEqual("blocked", result.status)
        self.assertEqual("UNSAFE_OR_UNSUPPORTED_SOURCE_URL", result.error_code)
        self.assertFalse(called)

    def test_configured_source_does_not_count_as_a_failed_probe(self) -> None:
        db.ensure_source_health("ashby")
        db.record_source_health("ashby", "configured")
        source = next(item for item in db.health_snapshot()["sources"] if item["source"] == "ashby")
        self.assertEqual(0, source["successful_checks"])
        self.assertEqual(0, source["failed_checks"])

    def test_cooldown_and_registered_probe_use_discovered_target_only(self) -> None:
        first = portal_sentinel.run_registered_probes(["greenhouse", "ashby"], fetcher=self.response(BASELINE_HTML))
        self.assertEqual(1, first["probed"])
        self.assertEqual(1, first["skipped"])
        self.assertEqual("baseline", first["results"][0]["status"])
        second = portal_sentinel.run_registered_probes(["greenhouse"], fetcher=self.response(BASELINE_HTML))
        self.assertEqual("cooldown", second["results"][0]["status"])
        self.assertEqual("disabled", second["external_execution"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

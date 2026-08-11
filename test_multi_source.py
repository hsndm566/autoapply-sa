#!/usr/bin/env python3
"""Offline regression + integration tests for the multi-source layer.

Covers phases 1-6 with fixtures and injected fetchers. No network, no Apify,
no Auditor bypass, no live submission. The Auditor gate (test_auditor.py) is
exercised separately and remains the authority on send/submit.

Run: python -m unittest -v test_multi_source
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in os.sys.path:
    os.sys.path.insert(0, str(HERE))

import job_schema as js
import source_registry as sr
import discovery as disc
import diversity as div
import path_verifier as pv


def fixture_bytes(name: str) -> bytes:
    return (HERE / "fixtures" / name).read_bytes()


class RegistryTests(unittest.TestCase):
    def test_registry_loaded_no_hardcoded_boards(self):
        reg = sr.load()
        self.assertIn("sources", reg)
        # Governance acceptance #1: a registry exists with Tier A sources.
        tiers = [s for s in reg["sources"] if s.get("tier") == "A"]
        self.assertGreaterEqual(len(tiers), 3)
        # No adapter module may hard-code board slugs (checked by grepping source).
        src = (HERE / "discovery.py").read_text(encoding="utf-8")
        # The string 'anthropic' must NOT appear as a hard-coded board list.
        self.assertNotIn('boards = ["anthropic"', src)


class SchemaDedupTests(unittest.TestCase):
    def _rec(self, source, pid, company, title, loc=""):
        return js.normalize_job(source=source, employer_key=company, posting_id=pid,
                                 company=company, title=title, location=loc)

    def test_hard_dedup_source_posting(self):
        a = self._rec("greenhouse", "1", "Acme", "Engineer")
        b = self._rec("greenhouse", "1", "Acme", "Engineer")  # identical
        kept, stats = js.dedup([a, b])
        self.assertEqual(stats["hard_removed"], 1)
        self.assertEqual(len(kept), 1)

    def test_soft_dedup_cross_post(self):
        a = self._rec("greenhouse", "11", "Acme", "Process Engineer", "Riyadh")
        b = self._rec("lever", "99", "Acme", "Process Engineer", "Riyadh")  # cross-post
        kept, stats = js.dedup([a, b])
        self.assertEqual(stats["soft_removed"], 1)
        self.assertEqual(len(kept), 1)

    def test_distinct_kept(self):
        a = self._rec("greenhouse", "1", "Acme", "Engineer", "Riyadh")
        b = self._rec("greenhouse", "2", "Globex", "Analyst", "Jeddah")
        kept, stats = js.dedup([a, b])
        self.assertEqual(len(kept), 2)
        self.assertEqual(stats["seen"], 2)


class DiscoveryFixtureTests(unittest.TestCase):
    def setUp(self):
        # Inject fixture fetchers keyed by URL substring.
        def fetcher(url: str) -> bytes:
            if "greenhouse" in url:
                return fixture_bytes("greenhouse_sample.json")
            if "api.lever.co" in url:
                return fixture_bytes("lever_sample.json")
            if "ashbyhq.com/posting-api" in url:
                return fixture_bytes("ashby_sample.json")
            return b""
        disc.set_fetcher(fetcher)

    def tearDown(self):
        disc.set_fetcher(None)

    def test_greenhouse_normalizes(self):
        emp = sr.employers_for_source("greenhouse")[0]
        recs = disc.fetch_greenhouse(emp)
        # fixture returns 4 jobs
        self.assertEqual(len(recs), 4)
        for r in recs:
            self.assertEqual(r["source"], "greenhouse")
            self.assertTrue(r["posting_id"])
            self.assertTrue(r["job_url"])

    def test_lever_normalizes(self):
        emp = sr.employers_for_source("lever")[0]
        recs = disc.fetch_lever(emp)
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["source"], "lever")

    def test_ashby_normalizes(self):
        emp = sr.employers_for_source("ashby")[0]
        recs = disc.fetch_ashby(emp)
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["source"], "ashby")

    def test_discover_all_no_apify(self):
        recs = disc.discover_all(fetch=True)
        self.assertGreater(len(recs), 0)
        # No Apify token / client is referenced in the fetch path.
        src = (HERE / "discovery.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("apify_api_key", src)
        self.assertNotIn("apify.com/v2", src)


class DiversityTests(unittest.TestCase):
    def _rec(self, company, source):
        return js.normalize_job(source=source, employer_key=company, posting_id=company,
                                 company=company, title="Engineer")

    def test_employer_cap(self):
        recs = [self._rec("Acme", "greenhouse") for _ in range(5)]
        kept, rep = div.enforce_diversity(recs, employer_cap=2)
        self.assertEqual(rep.dropped_employer_cap, 3)
        self.assertEqual(rep.kept, 2)

    def test_watchlist_cap(self):
        # 25 watchlisted + 0 others => must NOT all pass (10% ceiling).
        wl_recs = [self._rec("anthropic", "greenhouse") for _ in range(25)]
        kept, rep = div.enforce_diversity(wl_recs)
        self.assertLess(rep.employer_count, 25)
        self.assertGreater(rep.dropped_watchlist_cap, 0)

    def test_role_city_expansion(self):
        roles = div.expand_roles("industrial engineer")
        self.assertIn("Process Engineer", roles)
        self.assertIn("Supply Chain Engineer", roles)
        cities = div.expand_cities()
        self.assertIn("Riyadh", cities)
        self.assertIn("Jeddah", cities)


class PathVerifierTests(unittest.TestCase):
    def _rec(self, source="greenhouse", company="Acme", title="Engineer"):
        return js.normalize_job(source=source, employer_key=company, posting_id="1",
                                 company=company, title=title)

    def test_closed_listing(self):
        d = pv.verify(self._rec(), raw_text="This position is closed.")
        self.assertEqual(d.state, "expired_or_duplicate")

    def test_login_captcha_stops(self):
        d = pv.verify(self._rec(), raw_text="Please complete the captcha to apply.")
        self.assertEqual(d.state, "login_or_captcha")
        self.assertFalse(d.eligible_for_submit)

    def test_direct_email_lane(self):
        # Fix 3: a verified employer/recruiter address MUST return direct_email,
        # routed to the existing audited email lane. Ineligible for portal submit.
        d = pv.verify(self._rec(), email_address="careers@acme.com")
        self.assertEqual(d.state, "direct_email")
        self.assertFalse(d.eligible_for_submit)
        self.assertIn("email lane", d.blocker)

    def test_complex_form(self):
        d = pv.verify(self._rec(), raw_text="Additional questions required.")
        self.assertEqual(d.state, "portal_complex")

    def test_upload_unproven_source_fails_closed(self):
        # Resume input seen BUT source not yet proven -> portal_upload_unverified
        # (held, not eligible). Fix 3: keep unverified blocked.
        d = pv.verify(self._rec(source="greenhouse"), resume_input_seen=True,
                      required_fields=["name", "email"])
        self.assertEqual(d.state, "portal_upload_unverified")
        self.assertFalse(d.eligible_for_submit)

    def test_upload_proven_source_eligible(self):
        # Fix 3: a source that has passed a real CV-upload E2E returns
        # portal_upload_verified (NOT portal_upload_unverified) and is eligible.
        pv.clear_verified_uploads()
        pv.mark_source_upload_verified("greenhouse")
        d = pv.verify(self._rec(source="greenhouse"), resume_input_seen=True,
                      required_fields=["name", "email"])
        self.assertEqual(d.state, "portal_upload_verified")
        self.assertTrue(d.eligible_for_submit)
        pv.clear_verified_uploads()


class PipelineIntegrationTests(unittest.TestCase):
    """End-to-end offline: discover (fixtures) -> dedup -> diversity -> verify."""

    def setUp(self):
        def fetcher(url: str) -> bytes:
            if "greenhouse" in url:
                return fixture_bytes("greenhouse_sample.json")
            if "api.lever.co" in url:
                return fixture_bytes("lever_sample.json")
            if "ashbyhq.com/posting-api" in url:
                return fixture_bytes("ashby_sample.json")
            return b""
        disc.set_fetcher(fetcher)

    def tearDown(self):
        disc.set_fetcher(None)

    def test_discover_dedup_diversity_verify(self):
        raw = disc.discover_all(fetch=True)
        self.assertGreater(len(raw), 0)
        kept, _ = js.dedup(raw)
        diversified, _ = div.enforce_diversity(kept)
        # Path verification; no source marked upload-verified yet.
        decisions = [pv.verify(r) for r in diversified]
        # No decision may be eligible_for_submit (no proven upload source).
        self.assertTrue(all(not d.eligible_for_submit for d in decisions))
        # Confirm distinct SOURCES present (fixtures share one employer name).
        sources = {d.source for d in decisions}
        self.assertGreater(len(sources), 1)
        self.assertIn("greenhouse", sources)
        self.assertIn("ashby", sources)
        # Lever is intentionally DISABLED until independently verified, so it must
        # NOT appear in the live-discovery set (governance: no slug guessing).
        self.assertNotIn("lever", sources)


class LeverAcceptanceTests(unittest.TestCase):
    """Lever must NOT be admitted by guessing slugs (governance directive)."""

    def test_lever_disabled_until_verified(self):
        # With no verified boards in the registry, Lever stays out of the live set.
        self.assertFalse(sr.lever_enabled())
        # discover_source must short-circuit and return nothing for lever.
        self.assertEqual(disc.discover_source("lever", fetch=True), [])

    def test_verify_rejects_unverified_slug(self):
        # Guessing a plausible-but-unverified client must be rejected by the gate.
        # Uses the documented endpoint; a non-existent client returns 404 -> not accepted.
        # Network-guarded: only runs where egress is available.
        try:
            import urllib.request
            urllib.request.urlopen("https://boards-api.greenhouse.io", timeout=5)
        except Exception:
            self.skipTest("no network egress; skipping live Lever gate check")
        res = sr.verify_lever_board("this-client-does-not-exist-xyz", "https://example.com/careers")
        self.assertFalse(res["accepted"])
        self.assertFalse(res["endpoint_ok"])


class FixVerificationTests(unittest.TestCase):
    """Regression tests for the four independent-review fixes."""

    def _rec(self, source="greenhouse", company="Acme", title="Engineer"):
        return js.normalize_job(source=source, employer_key=company, posting_id="1",
                                 company=company, title=title)

    # --- Fix 2: apply URL preference (actual application URL, not detail page) ---
    def test_lever_prefers_applyurl(self):
        def fetcher(url: str) -> bytes:
            if "api.lever.co" in url:
                return fixture_bytes("lever_sample.json")
            return b""
        disc.set_fetcher(fetcher)
        try:
            recs = disc.fetch_lever({"name": "SampleCo", "client": "sampleco"})
            by_id = {r["posting_id"]: r for r in recs}
            # LV2001 has both hostedUrl and applyUrl -> apply_url must be applyUrl.
            self.assertEqual(by_id["LV2001"]["apply_url"], "https://jobs.lever.co/sampleco/LV2001/apply")
            self.assertNotEqual(by_id["LV2001"]["apply_url"], by_id["LV2001"]["job_url"])
            # LV2003 has only hostedUrl -> falls back to hostedUrl.
            self.assertEqual(by_id["LV2003"]["apply_url"], "https://jobs.lever.co/sampleco/LV2003")
        finally:
            disc.set_fetcher(None)

    def test_ashby_prefers_applyurl(self):
        def fetcher(url: str) -> bytes:
            if "ashbyhq.com/posting-api" in url:
                return fixture_bytes("ashby_sample.json")
            return b""
        disc.set_fetcher(fetcher)
        try:
            recs = disc.fetch_ashby({"name": "SampleCo", "org": "sampleco"})
            by_id = {r["posting_id"]: r for r in recs}
            # AS3001 has both jobUrl and applyUrl -> apply_url must be applyUrl.
            self.assertEqual(by_id["AS3001"]["apply_url"], "https://jobs.ashbyhq.com/sampleco/AS3001/apply")
            self.assertNotEqual(by_id["AS3001"]["apply_url"], by_id["AS3001"]["job_url"])
            # AS3003 has only jobUrl -> falls back to jobUrl.
            self.assertEqual(by_id["AS3003"]["apply_url"], "https://jobs.ashbyhq.com/sampleco/AS3003")
        finally:
            disc.set_fetcher(None)

    # --- Fix 3: state semantics ---
    def test_verified_email_returns_direct_email(self):
        d = pv.verify(self._rec(), email_address="talent@acme.com")
        self.assertEqual(d.state, "direct_email")
        self.assertFalse(d.eligible_for_submit)
        self.assertIn("email lane", d.blocker)

    def test_unverified_upload_blocked(self):
        pv.clear_verified_uploads()
        d = pv.verify(self._rec(source="greenhouse"), resume_input_seen=True,
                      required_fields=["name", "email"])
        self.assertEqual(d.state, "portal_upload_unverified")
        self.assertFalse(d.eligible_for_submit)

    def test_proven_upload_returns_verified(self):
        pv.clear_verified_uploads()
        pv.mark_source_upload_verified("greenhouse")
        d = pv.verify(self._rec(source="greenhouse"), resume_input_seen=True,
                      required_fields=["name", "email"])
        self.assertEqual(d.state, "portal_upload_verified")
        self.assertTrue(d.eligible_for_submit)
        pv.clear_verified_uploads()

    # --- Fix 4: Lever registry persistence + general source status ---
    def test_lever_status_honored_general(self):
        # Lever source status is "disabled" in the registry -> discover_source skips it
        # via the general status check (not a special-case Lever flag).
        self.assertEqual(disc.discover_source("lever", fetch=True), [])

    def test_admit_lever_persists_slug_and_meta(self):
        # Verify the persistence contract: dedicated client slug, careers URL,
        # verification timestamp, and verification result are written after BOTH
        # checks pass. Runs against a TEMP registry copy so the real registry is
        # never polluted (no committed test slug). Fully offline/deterministic.
        import tempfile, shutil, os as _os
        src = sr.REGISTRY_PATH
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False).name
        shutil.copyfile(src, tmp)
        old_path = sr.REGISTRY_PATH
        sr.REGISTRY_PATH = tmp
        sr.reload()
        try:
            # Patch admit's internal verify to pass (both checks ok).
            def fake_verify(client, careers_url):
                return {"accepted": True, "client": client, "careers_url": careers_url,
                        "careers_ok": True, "endpoint_ok": True}

            orig = sr.verify_lever_board
            sr.verify_lever_board = fake_verify
            try:
                # Admit a slug that does NOT match any existing employer name.
                res = sr.admit_lever_board("acme-real-slug", "https://careers.acme.com", commit=True)
                self.assertTrue(res["accepted"])
            finally:
                sr.verify_lever_board = orig

            reg = sr.load()
            lever = next(s for s in reg["sources"] if s["id"] == "lever")
            persisted = [e for e in lever["employers"] if e.get("client") == "acme-real-slug"]
            self.assertTrue(persisted, "dedicated client slug not persisted")
            e = persisted[0]
            self.assertEqual(e["careers_url"], "https://careers.acme.com")
            self.assertIn("verified_at", e)
            self.assertIn("verification_result", e)
            self.assertTrue(e["verified"])
            # Slug is independent of an existing employer's display name.
            patreon = next((x for x in lever["employers"] if x.get("client") == "patreon"), None)
            self.assertIsNotNone(patreon)
            self.assertEqual(patreon["name"], "Patreon")  # name preserved, not the slug
            self.assertNotEqual(patreon.get("name"), "acme-real-slug")
        finally:
            sr.REGISTRY_PATH = old_path
            sr.reload()
            _os.unlink(tmp)


if __name__ == "__main__":
    unittest.main(verbosity=2)

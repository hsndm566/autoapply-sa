#!/usr/bin/env python3
"""Phase 1 read-only test: source registry + adapters + schema + dedup + caps + Path Verifier.

Read-only by construction: runs the existing pipeline over fixtures and prints a
report. No network submission, no email, no Auditor change, no deploy.

Run: python phase1_readonly_test.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import job_schema as js
import source_registry as sr
import discovery as disc
import diversity as div
import path_verifier as pv

FIXTURES = {
    "greenhouse": "greenhouse_sample.json",
    "lever": "lever_sample.json",
    "ashby": "ashby_sample.json",
}


def _fixture_fetcher(url: str) -> bytes:
    for src, fname in FIXTURES.items():
        if src in url:
            p = HERE / "fixtures" / fname
            if p.exists():
                return p.read_bytes()
    return b""


def categorize_role_lane(title: str) -> str:
    """Map a job title to a campaign role lane using diversity.ROLE_LANES."""
    t = (title or "").lower()
    for key, lanes in div.ROLE_LANES.items():
        if key in t or any(lane.lower() in t for lane in lanes):
            return key
    return "other"


def main() -> int:
    disc.set_fetcher(_fixture_fetcher)

    # --- 1. Discover (fixtures stand in for read-only fetch) ---
    raw = disc.discover_all(fetch=True)

    # --- 2. Normalize + strict dedup ---
    kept, dstats = js.dedup(raw)

    # --- 3. Diversity caps (employer / source-family / watchlist) ---
    diversified, rep = div.enforce_diversity(kept)

    # --- 4. Path Verifier classification (no source marked upload-verified) ---
    pv.clear_verified_uploads()
    decisions = [pv.verify(r) for r in diversified]
    by_state = Counter(d.state for d in decisions)

    # Per-source and per-role-lane breakdowns (post-dedup + caps).
    per_source = Counter(r["source"] for r in diversified)
    per_role = Counter(categorize_role_lane(r["title"]) for r in diversified)
    unique_employers = sorted({r["company"] for r in diversified})

    direct_email = by_state.get("direct_email", 0)
    portal_upload = by_state.get("portal_upload_unverified", 0)
    blocked_complex = by_state.get("portal_complex", 0)
    login_captcha = by_state.get("login_or_captcha", 0)
    expired = by_state.get("expired_or_duplicate", 0)

    report = {
        "mode": "READ-ONLY (fixtures; no live submit, no email, no Auditor change, no deploy)",
        "raw_listings_seen": dstats["seen"],
        "unique_employers": unique_employers,
        "unique_employer_count": len(unique_employers),
        "jobs_per_source_post_caps": dict(per_source),
        "jobs_per_role_lane": dict(per_role),
        "duplicate_count": {
            "hard_source_posting_removed": dstats["hard_removed"],
            "soft_cross_post_removed": dstats["soft_removed"],
            "total_removed": dstats["hard_removed"] + dstats["soft_removed"],
        },
        "direct_email_options": direct_email,
        "portal_file_upload_candidates": portal_upload,
        "blocked_or_complex": {
            "portal_complex": blocked_complex,
            "login_or_captcha": login_captcha,
            "expired_or_duplicate": expired,
            "total_blocked": blocked_complex + login_captcha + expired,
        },
        "diversity_caps_applied": {
            "employer_cap_dropped": rep.dropped_employer_cap,
            "source_family_cap_dropped": rep.dropped_source_family_cap,
            "watchlist_cap_dropped": rep.dropped_watchlist_cap,
            "ready_for_50_options": rep.ready_for_50,
        },
        "live_canary_note": (
            "Separate read-only probe: Greenhouse public API = HTTP 200 (reachable). "
            "Lever/Ashby sample endpoints = HTTPError. Fixture counts above are the "
            "deterministic test basis; live per-source counts require a healthy "
            "source-specific adapter probe, not assumed."
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only live discovery + verification canary (Tier A sources).

Authorization: repair/validate Lever + Ashby adapters. NO submit, NO email, NO
deploy, NO Apify, NO Auditor change, NO CV upload. This only FETCHES public ATS
feeds and reads public apply-page HTML for upload-control markers.

Run: python live_canary.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import discovery as disc
import job_schema as js
import source_registry as sr
import path_verifier as pv

# Diverse real employers per source (NOT only AI giants; includes finance,
# industrial, consumer, KSA-relevant, devtools).
LIVE_SET = {
    "greenhouse": ["johnsoncontrols", "honeywell", "siemens", "caterpillar",
                   "saudiaramco", "shopify", "reddit", "lyft", "zoom", "figma"],
    "lever": ["patreon", "buffer", "brex", "wise", "ramp", "quora", "mattermost",
              "coinbase", "netflix", "databricks"],
    "ashby": ["linear", "ramp", "hebbia", "recall", "correctly", "openai",
              "notion", "anthropic", "databricks", "mercury"],
}

UA = {"User-Agent": "Mozilla/5.0 (compatible; AutoApplySA-Discovery/1.0)"}
_UPLOAD_RE = re.compile(r'type=["\']file["\']|name=["\'](resume|cv|attachment)', re.I)
_RESUME_WORD = re.compile(r"resume|curriculum vitae|\bcv\b", re.I)


def probe_upload_control(apply_url: str) -> dict:
    """Read-only GET of an apply page; report whether a file-upload control shows."""
    out = {"url": apply_url, "reachable": False, "file_input": False, "resume_mention": False}
    try:
        req = urllib.request.Request(apply_url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read(60000).decode("utf-8", "replace")
        out["reachable"] = True
        out["file_input"] = bool(_UPLOAD_RE.search(html))
        out["resume_mention"] = bool(_RESUME_WORD.search(html))
    except Exception:
        pass
    return out


def main() -> int:
    disc.clear_fetch_log()
    results = {"greenhouse": [], "lever": [], "ashby": []}
    apply_probes = []

    for source_id, boards in LIVE_SET.items():
        # Build temporary employer dicts from the live set (no registry mutation).
        for b in boards:
            emp = {"name": b, "board": b, "company": b, "org": b}
            fn = {
                "greenhouse": disc.fetch_greenhouse,
                "lever": disc.fetch_lever,
                "ashby": disc.fetch_ashby,
            }[source_id]
            try:
                recs = fn(emp)
            except Exception as e:
                recs = []
            results[source_id].extend(recs)
            # Probe up to 2 apply URLs per source for upload-control evidence.
            for r in recs[:2]:
                au = r.get("apply_url") or r.get("job_url")
                if au:
                    apply_probes.append((source_id, b, probe_upload_control(au)))

    log = disc.get_fetch_log()

    # Aggregate board outcomes.
    boards_ok = defaultdict(list)
    boards_fail = defaultdict(list)
    for e in log:
        if e["ok"]:
            boards_ok[e["employer"]].append(e)
        else:
            boards_fail[e["employer"]].append(e)

    # Normalize + dedup for unique employer/role reporting.
    raw = [r for sub in results.values() for r in sub]
    kept, dstats = js.dedup(raw)
    unique_employers = sorted({r["company"] for r in kept})
    roles = sorted({(r["title"] or "").strip() for r in kept if r.get("title")})
    valid_apply = sorted({r.get("apply_url") or r.get("job_url") for r in kept if r.get("apply_url") or r.get("job_url")})

    # Map upload-control evidence back onto records by apply_url, BEFORE verify.
    evidence_by_url = {p["url"]: p for (_, _, p) in apply_probes}
    for r in kept:
        au = r.get("apply_url") or r.get("job_url")
        if au and au in evidence_by_url and evidence_by_url[au].get("file_input"):
            r["_resume_input_seen"] = True

    # Path-verify the kept set. Use the read-only upload-control evidence per
    # record; no source is marked upload-verified, so every "file input seen"
    # record lands in portal_upload_unverified (held, not eligible).
    pv.clear_verified_uploads()
    decisions = []
    for r in kept:
        decisions.append(pv.verify(
            r,
            resume_input_seen=r.get("_resume_input_seen", False),
            required_fields=["resume"] if r.get("_resume_input_seen") else None,
        ))
    state_counts = Counter(d.state for d in decisions)

    # Rate-limit / backoff behavior from the fetch log.
    retries_seen = [e["retries"] for e in log if e["retries"] > 0]
    reasons = Counter(e["reason"] for e in log if not e["ok"])

    report = {
        "mode": "READ-ONLY live canary. No submit, email, deploy, Apify, or Auditor change.",
        "live_successful_boards_per_source": {
            s: sorted({r["company"] for r in results[s]}) for s in LIVE_SET
        },
        "raw_listings_fetched": len(raw),
        "unique_employers": unique_employers,
        "unique_employer_count": len(unique_employers),
        "unique_roles": roles,
        "unique_role_count": len(roles),
        "valid_apply_urls_found": len(valid_apply),
        "valid_apply_url_sample": valid_apply[:10],
        "board_failures_by_reason": dict(reasons),
        "boards_failed": {e["employer"]: e["reason"] for e in log if not e["ok"]},
        "source_rate_limit_backoff": {
            "transient_retries_observed": retries_seen,
            "max_retries_configured": 3,
            "note": "Transient 429/5xx/timeout retried with 2**attempt backoff; 401/403/404 fail closed (no retry).",
        },
        "cv_upload_control_probes": [
            {"source": s, "employer": emp, **probe} for (s, emp, probe) in apply_probes
        ],
        "upload_control_summary": {
            "pages_probed": len(apply_probes),
            "reachable": sum(1 for _, _, p in apply_probes if p["reachable"]),
            "file_input_detected": sum(1 for _, _, p in apply_probes if p["file_input"]),
            "resume_mention_detected": sum(1 for _, _, p in apply_probes if p["resume_mention"]),
        },
        "path_state_counts": dict(state_counts),
        "source_ready_for_live_submission": None,
        "readiness_note": "Discovery/verification only. No source marked upload-verified; nothing eligible for submit.",
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

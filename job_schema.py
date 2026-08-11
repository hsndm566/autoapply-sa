#!/usr/bin/env python3
"""Shared normalized job schema and strict deduplication.

Every discovery adapter maps its raw listing into the same ``JobRecord`` before
scoring, matching, or path-verification. Deduplication runs in two passes:

1. HARD dedup on ``source + posting_id`` (authoritative; never override).
2. SOFT dedup on a company/title/location fingerprint (catches cross-posts
   where the same role is listed on two boards with different posting ids).

Immutability: records are plain dicts; the fingerprint helpers are pure.
Read-only with respect to the network — these helpers never fetch.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

# Truthful job lifecycle states from the integration plan.
STATES = (
    "discovered", "normalized", "deduplicated", "matched", "path_verified",
    "drafted", "audit_approved", "submitted_verified", "needs_review",
    "blocked",
)

# Path Verifier classifications.
PATH_STATES = (
    "direct_email", "portal_upload_verified", "portal_upload_unverified",
    "portal_complex", "login_or_captcha", "expired_or_duplicate",
)


def normalize_job(
    *,
    source: str,
    employer_key: str,
    posting_id: str,
    company: str,
    title: str,
    location: str = "",
    remote: bool = False,
    employment_type: str = "Unknown",
    posted_at: str = "",
    job_url: str = "",
    apply_url: str = "",
    description: str = "",
    application_mode: str = "unknown",
    required_fields: list[str] | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one normalized job record. ``raw`` preserves source evidence."""
    return {
        "source": source,
        "employer_key": employer_key,
        "posting_id": str(posting_id),
        "company": company,
        "title": title,
        "location": location,
        "remote": bool(remote),
        "employment_type": employment_type,
        "posted_at": posted_at,
        "job_url": job_url,
        "apply_url": apply_url or job_url,
        "description": description or "",
        "application_mode": application_mode,
        "required_fields": list(required_fields or []),
        "fetched_at": "",
        "_state": "normalized",
        "_path": None,
        "_raw": raw or {},
    }


def hard_key(rec: dict[str, Any]) -> str:
    """Authoritative dedup key: source + posting_id."""
    return f"{rec.get('source','')}|{rec.get('posting_id','')}"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def soft_key(rec: dict[str, Any]) -> str:
    """Softer cross-post key: company + title + location fingerprint."""
    company = _norm(rec.get("company", ""))
    title = _norm(rec.get("title", ""))
    loc = _norm(rec.get("location", ""))
    return hashlib.sha256(f"{company}|{title}|{loc}".encode()).hexdigest()


def dedup(records: Iterable[dict[str, Any]], seen_hard: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Strict two-pass dedup.

    Returns (kept_records, stats) where stats reports:
      - seen: total input
      - hard_removed: dropped because source+posting_id already known
      - soft_removed: dropped as a cross-post duplicate (same company/title/loc)
    ``seen_hard`` lets the caller carry known keys across runs/DB layers.
    """
    seen_hard = set(seen_hard or [])
    seen_soft: set[str] = set()
    kept: list[dict[str, Any]] = []
    stats = {"seen": 0, "hard_removed": 0, "soft_removed": 0}
    for rec in records:
        stats["seen"] += 1
        hk = hard_key(rec)
        if hk in seen_hard:
            stats["hard_removed"] += 1
            continue
        sk = soft_key(rec)
        if sk in seen_soft:
            stats["soft_removed"] += 1
            continue
        seen_hard.add(hk)
        seen_soft.add(sk)
        rec = dict(rec)
        rec["_state"] = "deduplicated"
        kept.append(rec)
    return kept, stats

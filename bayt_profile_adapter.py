"""Bayt profile-aware routing for AutoApply SA.

This adapter deliberately manages *eligibility and queue state*, not credentialed
browser execution. A Railway service cannot safely reuse a user's local Bayt
session; actual Easy Apply remains a browser handoff after the Auditor approves
an exact package. CAPTCHA, Cloudflare, MFA, login, and terms acceptance always
remain user-completed steps.
"""
from __future__ import annotations

import os
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ADAPTER_ID = "bayt_profile_handoff_v1"
EXECUTION_MODE = "browser_handoff_only"


@dataclass(frozen=True)
class BaytRouteDecision:
    lead_id: int
    job_url: str
    status: str
    reason: str
    adapter_id: str = ADAPTER_ID
    execution_mode: str = EXECUTION_MODE

    def as_dict(self) -> dict[str, str | int]:
        return asdict(self)


def is_bayt_job_url(value: str) -> bool:
    parsed = urlparse(str(value or ""))
    return parsed.scheme == "https" and parsed.netloc in {"www.bayt.com", "bayt.com"} and "/jobs/" in parsed.path


def profile_ready() -> bool:
    """Return only the explicit deployment flag; never inspect browser cookies."""
    return os.environ.get("BAYT_BROWSER_PROFILE_READY", "false").lower() == "true"


def decide(lead_id: int, job_url: str, *, current_status: str, browser_profile_ready: bool | None = None) -> BaytRouteDecision:
    if not is_bayt_job_url(job_url):
        return BaytRouteDecision(lead_id, job_url, "blocked", "BAYT_URL_NOT_ALLOWED")
    if current_status == "submitted":
        return BaytRouteDecision(lead_id, job_url, "already_submitted", "SUBMISSION_ALREADY_RECORDED")
    if not (profile_ready() if browser_profile_ready is None else browser_profile_ready):
        return BaytRouteDecision(lead_id, job_url, "waiting_for_profile", "BAYT_BROWSER_PROFILE_NOT_CONFIRMED")
    return BaytRouteDecision(lead_id, job_url, "browser_handoff_ready", "AUDITOR_APPROVAL_AND_USER_BROWSER_HANDOFF_REQUIRED")


def queue_summary(db_path: str | Path) -> dict[str, Any]:
    """Summarize Bayt leads without contacting Bayt or changing database state."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, url, status FROM discovered_jobs WHERE url LIKE '%bayt.com/%'"
        ).fetchall()
    finally:
        conn.close()
    decisions = [decide(int(row[0]), str(row[1] or ""), current_status=str(row[2] or "")) for row in rows]
    counts = Counter(item.status for item in decisions)
    return {
        "adapter_id": ADAPTER_ID,
        "execution_mode": EXECUTION_MODE,
        "profile_ready": profile_ready(),
        "total_bayt_leads": len(decisions),
        "by_route_status": dict(sorted(counts.items())),
        "submitted_leads": [item.lead_id for item in decisions if item.status == "already_submitted"],
    }


__all__ = ["ADAPTER_ID", "EXECUTION_MODE", "BaytRouteDecision", "decide", "is_bayt_job_url", "profile_ready", "queue_summary"]

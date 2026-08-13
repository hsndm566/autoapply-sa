"""Read-only, source-balanced browser-handoff selection for portal leads.

This module selects the *next forms to inspect*, not forms to submit. It never
uses credentials, uploads files, invokes an AI reviewer, or makes network calls.
Final submission remains conditional on verified CV transport, factual answers,
a current Auditor approval, and a working browser handoff.
"""
from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EMPLOYER_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
SOURCE_BUNDLE_CAP = 2
RETRY_COOLDOWN_SECONDS = 48 * 60 * 60
RETRYABLE_STATUSES = {"browser_timeout", "form_changed", "transient_error"}
MANUAL_BLOCKER_STATUSES = {"captcha", "login_required", "unsupported_question", "abandoned", "submitted"}
MAX_RETRY_ATTEMPTS = 2
TERMINAL_APPLICATION_STATUSES = {"submitted", "audit_approved", "queued_submit"}


def source_for_url(url: str) -> str:
    host = urlparse(str(url or "")).netloc.casefold()
    if "bayt.com" in host:
        return "bayt"
    if "ashbyhq.com" in host:
        return "ashby"
    if "greenhouse.io" in host:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "indeed." in host:
        return "indeed"
    if "linkedin.com" in host:
        return "linkedin"
    return "employer_site"


def _normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def employer_key(company: str, url: str, title: str) -> str:
    normalized = _normal(company)
    if normalized:
        return f"company:{normalized}"
    host = urlparse(str(url or "")).netloc.casefold() or "unknown"
    return f"anonymous:{host}:{_normal(title)}"


def role_family(title: str) -> str:
    normalized = _normal(title)
    for family, tokens in (
        ("food_service", ("barista", "waiter", "waitress", "server", "food", "chef", "hospitality")),
        ("customer_service", ("customer", "contact center", "call center", "guest", "reception")),
        ("sales", ("sales", "account manager", "business development", "retail")),
        ("administration", ("admin", "assistant", "coordinator", "operations", "office")),
        ("engineering", ("engineer", "technical", "data scientist", "developer")),
    ):
        if any(token in normalized for token in tokens):
            return family
    words = normalized.split()
    return " ".join(words[:2]) or "other"


@dataclass(frozen=True)
class HandoffCandidate:
    lead_id: int
    company: str
    title: str
    location: str
    url: str
    source: str
    role_family: str
    handoff_state: str
    handoff_reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _recent_employer_keys(connection: sqlite3.Connection, now: float) -> set[str]:
    rows = connection.execute(
        """
        SELECT company, role FROM applications
        WHERE status IN ({}) AND updated_at >= ?
        """.format(",".join("?" for _ in TERMINAL_APPLICATION_STATUSES)),
        [*sorted(TERMINAL_APPLICATION_STATUSES), now - EMPLOYER_COOLDOWN_SECONDS],
    ).fetchall()
    return {employer_key(str(row[0] or ""), "", str(row[1] or "")) for row in rows}


def _retry_blocked(connection: sqlite3.Connection, url: str, now: float) -> bool:
    # The discovered_jobs table only holds current lead state. A queued lead whose
    # URL already maps to a recent retryable attempt is kept out of this selector.
    # Older databases that predate the observability table remain readable.
    try:
        row = connection.execute(
            "SELECT status, updated_at, attempt_count FROM browser_handoff_attempts WHERE job_url=?", (url,)
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    if row is None:
        return False
    status, updated_at, attempt_count = str(row[0] or ""), float(row[1] or 0), int(row[2] or 0)
    if status in MANUAL_BLOCKER_STATUSES:
        return True
    if status in RETRYABLE_STATUSES:
        return attempt_count >= MAX_RETRY_ATTEMPTS or updated_at >= now - RETRY_COOLDOWN_SECONDS
    return False


def select_handoffs(db_path: str | Path, *, limit: int = 10, bayt_profile_ready: bool = False, now: float | None = None) -> list[HandoffCandidate]:
    """Return a diversified, non-submitting inspection queue.

    A Bayt profile enables browser inspection only; it does not mean that a job
    has passed the upload, questionnaire, CAPTCHA, or Auditor gates.
    """
    if not 1 <= limit <= 25:
        raise ValueError("limit must be between 1 and 25")
    timestamp = time.time() if now is None else float(now)
    connection = sqlite3.connect(str(db_path))
    try:
        blocked_employers = _recent_employer_keys(connection, timestamp)
        rows = connection.execute(
            """
            SELECT id, title, company, location, url
            FROM discovered_jobs
            WHERE status='new' AND url LIKE 'http%'
            ORDER BY id ASC
            """
        ).fetchall()
        eligible: list[HandoffCandidate] = []
        for lead_id, title, company, location, url in rows:
            value_url = str(url or "")
            if _retry_blocked(connection, value_url, timestamp):
                continue
            source = source_for_url(value_url)
            key = employer_key(str(company or ""), value_url, str(title or ""))
            if key in blocked_employers:
                continue
            if source == "bayt" and bayt_profile_ready:
                state, reason = "browser_inspection_ready", "BAYT_PROFILE_READY_FORM_AND_UPLOAD_STILL_REQUIRE_VERIFICATION"
            else:
                state, reason = "source_verification_required", "SOURCE_SPECIFIC_UPLOAD_AND_BROWSER_PROOF_REQUIRED"
            eligible.append(HandoffCandidate(
                lead_id=int(lead_id), company=str(company or ""), title=str(title or ""),
                location=str(location or ""), url=value_url, source=source,
                role_family=role_family(str(title or "")), handoff_state=state, handoff_reason=reason,
            ))

        selected: list[HandoffCandidate] = []
        selected_employers: set[str] = set()
        source_counts: Counter[str] = Counter()
        last_family = ""
        remaining = eligible[:]
        while remaining and len(selected) < limit:
            candidates = [
                item for item in remaining
                if employer_key(item.company, item.url, item.title) not in selected_employers
            ]
            if not candidates:
                break
            pool = [item for item in candidates if source_counts[item.source] < SOURCE_BUNDLE_CAP]
            if not pool:
                break
            chosen = min(
                pool,
                key=lambda item: (
                    source_counts[item.source],
                    1 if item.role_family == last_family else 0,
                    item.lead_id,
                ),
            )
            selected.append(chosen)
            selected_employers.add(employer_key(chosen.company, chosen.url, chosen.title))
            source_counts[chosen.source] += 1
            last_family = chosen.role_family
            remaining = [item for item in remaining if item.lead_id != chosen.lead_id]
        return selected
    finally:
        connection.close()


def queue_summary(db_path: str | Path, *, limit: int = 10, bayt_profile_ready: bool = False) -> dict[str, Any]:
    selected = select_handoffs(db_path, limit=limit, bayt_profile_ready=bayt_profile_ready)
    return {
        "policy_version": "diversity_v1",
        "execution_mode": "browser_handoff_only",
        "submits_applications": False,
        "employer_cooldown_days": EMPLOYER_COOLDOWN_SECONDS // 86400,
        "source_bundle_cap": SOURCE_BUNDLE_CAP,
        "maximum_retry_attempts": MAX_RETRY_ATTEMPTS,
        "selected": [item.as_dict() for item in selected],
        "selected_by_source": dict(sorted(Counter(item.source for item in selected).items())),
        "selected_by_role_family": dict(sorted(Counter(item.role_family for item in selected).items())),
    }


__all__ = ["HandoffCandidate", "queue_summary", "select_handoffs", "source_for_url"]

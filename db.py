"""Durable state for AutoApply SA.

This module is intentionally provider-neutral.  It owns campaign state, the legacy
application state machine, evidence, outbox rows, and operational health records.
It uses SQLite by default and is designed to live on a mounted volume.  No function
in this module sends an email, submits a form, or calls an AI model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterable
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "autoapply.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS discovered_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    company TEXT,
    location TEXT,
    url TEXT UNIQUE,
    description TEXT,
    easy_apply BOOLEAN,
    category TEXT,
    status TEXT DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    job_posting_hash TEXT NOT NULL UNIQUE,
    company TEXT,
    role TEXT,
    status TEXT NOT NULL DEFAULT 'scraped',
    attempt_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS browser_handoff_attempts (
    job_url TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_detail TEXT,
    updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,
    job_posting_hash TEXT,
    stage TEXT,
    error TEXT,
    created_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS run_flags (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS run_budget (
    action_type TEXT PRIMARY KEY,
    max_per_hour INTEGER DEFAULT 20,
    max_per_run INTEGER DEFAULT 50
);

CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    access_token_hash TEXT NOT NULL,
    candidate_name TEXT NOT NULL,
    candidate_email TEXT NOT NULL,
    target_role TEXT NOT NULL,
    city TEXT,
    industry TEXT,
    seniority TEXT,
    language TEXT,
    cv_path TEXT,
    cv_original_name TEXT,
    cv_sha256 TEXT,
    status TEXT NOT NULL DEFAULT 'intake_received',
    execution_enabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS campaign_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS campaign_jobs (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    job_hash TEXT NOT NULL,
    source TEXT,
    company TEXT,
    title TEXT,
    location TEXT,
    job_url TEXT,
    path_state TEXT NOT NULL DEFAULT 'discovered',
    fit_score REAL,
    status TEXT NOT NULL DEFAULT 'discovered',
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now')),
    UNIQUE(campaign_id, job_hash),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS action_outbox (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    campaign_job_id TEXT,
    action_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    available_at REAL DEFAULT (strftime('%s','now')),
    locked_at REAL,
    completed_at REAL,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_job_id) REFERENCES campaign_jobs(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS outreach_contacts (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT,
    company TEXT,
    role TEXT,
    status TEXT NOT NULL DEFAULT 'unverified',
    verification_source TEXT,
    last_contacted_at REAL,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS campaign_contact_attempts (
    campaign_id TEXT NOT NULL,
    contact_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'available',
    outbox_id TEXT,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now')),
    PRIMARY KEY(campaign_id, contact_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (contact_id) REFERENCES outreach_contacts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS application_evidence (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    campaign_job_id TEXT,
    evidence_type TEXT NOT NULL,
    value TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL DEFAULT (strftime('%s','now')),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (campaign_job_id) REFERENCES campaign_jobs(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'unknown',
    successful_checks INTEGER NOT NULL DEFAULT 0,
    failed_checks INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    last_checked_at REAL,
    updated_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS portal_probe_runs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    adapter_id TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    target_url TEXT NOT NULL,
    status TEXT NOT NULL,
    fingerprint TEXT,
    previous_fingerprint TEXT,
    observation_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    observed_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS service_health (
    check_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    detail TEXT,
    checked_at REAL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_browser_handoff_updated ON browser_handoff_attempts(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_client ON applications(client_id);
CREATE INDEX IF NOT EXISTS idx_campaign_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaign_events ON campaign_events(campaign_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaign_jobs ON campaign_jobs(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_outbox_ready ON action_outbox(status, available_at);
CREATE INDEX IF NOT EXISTS idx_outbox_type_status ON action_outbox(action_type, status, available_at);
CREATE INDEX IF NOT EXISTS idx_outreach_contacts_status ON outreach_contacts(status, company);
CREATE INDEX IF NOT EXISTS idx_evidence_campaign ON application_evidence(campaign_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaign_discovery_events ON campaign_events(campaign_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_portal_probe_source_observed ON portal_probe_runs(source, observed_at DESC);
"""


def _now() -> float:
    return time.time()


def _json(value: Any) -> str:
    return json.dumps(value or {}, separators=(",", ":"), ensure_ascii=False)


def _required_text(value: Any, field_name: str, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()[:limit]


def _validated_email(value: Any) -> str:
    email = _required_text(value, "candidate_email", 320).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("candidate_email is invalid")
    return email


def _validated_http_url(value: Any, field_name: str) -> str:
    url = _required_text(value, field_name, 2000)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    return url


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


@contextmanager
def connection() -> Iterable[sqlite3.Connection]:
    directory = os.path.dirname(os.path.abspath(DB_PATH))
    if directory:
        os.makedirs(directory, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA foreign_keys=ON;")
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def conn() -> sqlite3.Connection:
    """Compatibility helper for older modules; callers must close the connection."""
    directory = os.path.dirname(os.path.abspath(DB_PATH))
    if directory:
        os.makedirs(directory, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA foreign_keys=ON;")
    c.executescript(SCHEMA)
    return c


def initialize() -> None:
    with connection() as c:
        c.execute("SELECT 1")


def import_discovered_jobs(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Idempotently import discovery leads without changing submitted/non-new remote state."""
    accepted = inserted = updated = skipped = 0
    with connection() as c:
        for raw in rows:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            url = str(raw.get("url") or "").strip()
            if not url.startswith(("https://", "http://")):
                skipped += 1
                continue
            title = str(raw.get("title") or "").strip()[:500]
            company = str(raw.get("company") or "").strip()[:500]
            if not title or not company:
                skipped += 1
                continue
            existing = c.execute("SELECT id FROM discovered_jobs WHERE url=?", (url,)).fetchone()
            c.execute(
                """
                INSERT INTO discovered_jobs(title, company, location, url, description, easy_apply, category, status)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(url) DO UPDATE SET
                  title=excluded.title,
                  company=excluded.company,
                  location=excluded.location,
                  description=excluded.description,
                  easy_apply=excluded.easy_apply,
                  category=excluded.category,
                  status=CASE WHEN discovered_jobs.status='new' THEN excluded.status ELSE discovered_jobs.status END
                """,
                (
                    title,
                    company,
                    str(raw.get("location") or "").strip()[:500],
                    url,
                    str(raw.get("description") or "")[:20000],
                    bool(raw.get("easy_apply", False)),
                    str(raw.get("category") or "other").strip()[:120] or "other",
                    str(raw.get("status") or "new").strip()[:120] or "new",
                ),
            )
            accepted += 1
            if existing is None:
                inserted += 1
            else:
                updated += 1
    return {"accepted": accepted, "inserted": inserted, "updated": updated, "skipped": skipped}


def posting_hash(company: str, role: str, url: str = "") -> str:
    return hashlib.sha256(f"{company}|{role}|{url}".encode("utf-8")).hexdigest()


BROWSER_HANDOFF_ATTEMPT_STATUSES = {
    "browser_timeout", "form_changed", "transient_error", "captcha", "login_required",
    "unsupported_question", "submitted", "abandoned", "eligibility_reopened",
}


def record_browser_handoff_attempt(job_url: str, status: str, detail: str = "") -> dict[str, Any]:
    """Persist browser inspection outcome only; this function cannot submit a form."""
    clean_url = str(job_url or "").strip()
    clean_status = str(status or "").strip()
    if not clean_url.startswith(("https://", "http://")):
        raise ValueError("job_url must be an absolute HTTP(S) URL")
    if clean_status not in BROWSER_HANDOFF_ATTEMPT_STATUSES:
        raise ValueError("unsupported browser handoff status")
    with connection() as c:
        c.execute(
            """
            INSERT INTO browser_handoff_attempts(job_url,status,attempt_count,last_detail,updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(job_url) DO UPDATE SET
                status=excluded.status,
                attempt_count=browser_handoff_attempts.attempt_count+1,
                last_detail=excluded.last_detail,
                updated_at=excluded.updated_at
            """,
            (clean_url, clean_status, 1, str(detail or "")[:500], _now()),
        )
        row = c.execute(
            "SELECT job_url,status,attempt_count,last_detail,updated_at FROM browser_handoff_attempts WHERE job_url=?",
            (clean_url,),
        ).fetchone()
    return dict(row) if row else {}


# ---- Legacy orchestrator compatibility -------------------------------------------------

def kill_switch_on() -> bool:
    with connection() as c:
        row = c.execute("SELECT value FROM run_flags WHERE key='RUN_ENABLED'").fetchone()
    return row is not None and row["value"] == "false"


def set_kill_switch(on: bool) -> None:
    with connection() as c:
        c.execute(
            "INSERT OR REPLACE INTO run_flags(key,value) VALUES('RUN_ENABLED',?)",
            ("false" if on else "true",),
        )


def ingest_job(client_id: str, company: str, role: str, url: str = "") -> tuple[str, bool]:
    h = posting_hash(company, role, url)
    with connection() as c:
        try:
            c.execute(
                "INSERT INTO applications(client_id,job_posting_hash,company,role,status) VALUES(?,?,?,?,?)",
                (client_id, h, company, role, "scraped"),
            )
            return h, True
        except sqlite3.IntegrityError:
            return h, False


def set_status(h: str, status: str, error: str | None = None) -> None:
    with connection() as c:
        c.execute(
            "UPDATE applications SET status=?,last_error=?,attempt_count=attempt_count+1,updated_at=? WHERE job_posting_hash=?",
            (status, error, _now(), h),
        )


def dead_letter(client_id: str, h: str, stage: str, error: Any) -> None:
    with connection() as c:
        c.execute(
            "INSERT INTO dead_letter(client_id,job_posting_hash,stage,error) VALUES(?,?,?,?)",
            (client_id, h, stage, str(error)[:500]),
        )


def action_count_window(action_type: str, window_secs: int = 3600) -> int:
    with connection() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM applications WHERE status IN ('submitted','queued_submit') AND updated_at > ?",
            (_now() - window_secs,),
        ).fetchone()
    return int(row["n"])


def action_count_run(action_type: str) -> int:
    with connection() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM applications WHERE status IN ('submitted','queued_submit')"
        ).fetchone()
    return int(row["n"])


def budget_for(action_type: str) -> tuple[int, int]:
    with connection() as c:
        row = c.execute(
            "SELECT max_per_hour, max_per_run FROM run_budget WHERE action_type=?", (action_type,)
        ).fetchone()
    return (int(row["max_per_hour"]), int(row["max_per_run"])) if row else (20, 50)


# ---- Campaign platform ----------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_campaign(
    *,
    candidate_name: str,
    candidate_email: str,
    target_role: str,
    city: str = "",
    industry: str = "",
    seniority: str = "",
    language: str = "",
    cv_path: str | None = None,
    cv_original_name: str | None = None,
    cv_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    clean_name = _required_text(candidate_name, "candidate_name", 200)
    clean_email = _validated_email(candidate_email)
    clean_role = _required_text(target_role, "target_role", 500)
    campaign_id = str(uuid.uuid4())
    access_token = secrets.token_urlsafe(32)
    now = _now()
    with connection() as c:
        c.execute(
            """INSERT INTO campaigns(
                id,access_token_hash,candidate_name,candidate_email,target_role,city,industry,
                seniority,language,cv_path,cv_original_name,cv_sha256,status,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                campaign_id, _token_hash(access_token), clean_name, clean_email, clean_role,
                str(city or "").strip(), str(industry or "").strip(), str(seniority or "").strip(), str(language or "").strip(),
                cv_path, cv_original_name, cv_sha256, "intake_received", now, now,
            ),
        )
    add_campaign_event(campaign_id, "campaign_created", "info", "Campaign intake received; no external action has started.")
    if cv_path:
        add_campaign_event(campaign_id, "cv_stored", "info", "CV file stored for controlled campaign processing.", {"filename": cv_original_name})
    return get_campaign(campaign_id) or {}, access_token


def get_campaign(campaign_id: str) -> dict[str, Any] | None:
    with connection() as c:
        row = c.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    return _row(row)


def campaign_authorized(campaign_id: str, access_token: str | None) -> bool:
    if not access_token:
        return False
    campaign = get_campaign(campaign_id)
    return bool(campaign and secrets.compare_digest(campaign["access_token_hash"], _token_hash(access_token)))


def activate_campaign(campaign_id: str) -> dict[str, Any] | None:
    with connection() as c:
        c.execute(
            "UPDATE campaigns SET status='active_readonly',updated_at=? WHERE id=? AND status IN ('intake_received','paused')",
            (_now(), campaign_id),
        )
    add_campaign_event(
        campaign_id,
        "campaign_activated",
        "info",
        "Campaign activated for discovery and drafting only. External submission remains disabled until a source proves CV upload and evidence capture.",
    )
    return get_campaign(campaign_id)


def pause_campaign(campaign_id: str, reason: str = "Paused by campaign owner") -> dict[str, Any] | None:
    with connection() as c:
        c.execute("UPDATE campaigns SET status='paused',updated_at=? WHERE id=?", (_now(), campaign_id))
    add_campaign_event(campaign_id, "campaign_paused", "warning", reason)
    return get_campaign(campaign_id)


def add_campaign_event(
    campaign_id: str,
    event_type: str,
    level: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    with connection() as c:
        c.execute(
            "INSERT INTO campaign_events(campaign_id,event_type,level,message,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
            (campaign_id, event_type, level, message[:2000], _json(metadata), _now()),
        )


def list_campaign_events(campaign_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with connection() as c:
        rows = c.execute(
            "SELECT id,campaign_id,event_type,level,message,metadata_json,created_at FROM campaign_events WHERE campaign_id=? ORDER BY created_at DESC LIMIT ?",
            (campaign_id, max(1, min(limit, 500))),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["metadata"] = json.loads(item.pop("metadata_json"))
        except json.JSONDecodeError:
            item["metadata"] = {}
        result.append(item)
    return result


def list_campaigns_with_status(status: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return campaign records for safe workers; access-token hashes are never exposed."""
    with connection() as c:
        rows = c.execute(
            """SELECT id,candidate_name,candidate_email,target_role,city,industry,seniority,language,
                      cv_path,cv_original_name,cv_sha256,status,execution_enabled,created_at,updated_at
               FROM campaigns WHERE status=? ORDER BY updated_at ASC LIMIT ?""",
            (status, max(1, min(limit, 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def campaign_event_within(campaign_id: str, event_type: str, seconds: int) -> bool:
    """Return true when an event exists within the provided cooldown window."""
    with connection() as c:
        row = c.execute(
            "SELECT 1 FROM campaign_events WHERE campaign_id=? AND event_type=? AND created_at>=? LIMIT 1",
            (campaign_id, event_type, _now() - max(0, seconds)),
        ).fetchone()
    return row is not None


def campaign_summary(campaign_id: str) -> dict[str, Any] | None:
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None
    with connection() as c:
        job_rows = c.execute(
            "SELECT status,COUNT(*) AS count FROM campaign_jobs WHERE campaign_id=? GROUP BY status", (campaign_id,)
        ).fetchall()
        evidence_count = c.execute(
            "SELECT COUNT(*) AS count FROM application_evidence WHERE campaign_id=?", (campaign_id,)
        ).fetchone()["count"]
        email_send_count = c.execute(
            "SELECT COUNT(*) AS count FROM application_evidence WHERE campaign_id=? AND evidence_type='email_smtp_accepted'", (campaign_id,)
        ).fetchone()["count"]
        last_application_row = c.execute(
            "SELECT MAX(created_at) AS created_at FROM application_evidence WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        evidence_rows = c.execute(
            """SELECT ae.id,ae.evidence_type,ae.campaign_job_id,ae.created_at,
                      cj.company,cj.title,cj.location
               FROM application_evidence ae
               LEFT JOIN campaign_jobs cj ON cj.id=ae.campaign_job_id
               WHERE ae.campaign_id=?
               ORDER BY ae.created_at DESC
               LIMIT 100""",
            (campaign_id,),
        ).fetchall()
        outbox_rows = c.execute(
            "SELECT status,COUNT(*) AS count FROM action_outbox WHERE campaign_id=? GROUP BY status", (campaign_id,)
        ).fetchall()
    campaign.pop("access_token_hash", None)
    campaign.pop("cv_path", None)
    campaign["job_counts"] = {row["status"]: row["count"] for row in job_rows}
    campaign["outbox_counts"] = {row["status"]: row["count"] for row in outbox_rows}
    campaign["evidence_count"] = evidence_count
    campaign["email_send_count"] = email_send_count
    campaign["last_application_at"] = last_application_row["created_at"] if last_application_row else None
    campaign["verified_applications"] = [
        {
            "id": row["id"],
            "evidence_type": row["evidence_type"],
            "campaign_job_id": row["campaign_job_id"],
            "company": row["company"],
            "title": row["title"],
            "location": row["location"],
            "created_at": row["created_at"],
        }
        for row in evidence_rows
    ]
    campaign["external_execution_enabled"] = bool(campaign["execution_enabled"])
    return campaign


def add_campaign_job(
    campaign_id: str,
    *,
    company: str,
    title: str,
    job_url: str,
    source: str = "",
    location: str = "",
    path_state: str = "discovered",
    fit_score: float | None = None,
) -> tuple[str, bool]:
    clean_company = _required_text(company, "company", 500)
    clean_title = _required_text(title, "title", 500)
    clean_url = _validated_http_url(job_url, "job_url")
    job_hash = posting_hash(clean_company, clean_title, clean_url)
    job_id = str(uuid.uuid4())
    with connection() as c:
        try:
            c.execute(
                """INSERT INTO campaign_jobs(
                   id,campaign_id,job_hash,source,company,title,location,job_url,path_state,fit_score,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, campaign_id, job_hash, str(source or "").strip()[:120], clean_company, clean_title, str(location or "").strip()[:500], clean_url, str(path_state or "discovered").strip()[:120], fit_score, "discovered", _now(), _now()),
            )
            return job_id, True
        except sqlite3.IntegrityError:
            row = c.execute(
                "SELECT id FROM campaign_jobs WHERE campaign_id=? AND job_hash=?", (campaign_id, job_hash)
            ).fetchone()
            return str(row["id"]), False


def upsert_outreach_contact(
    *,
    email: str,
    full_name: str = "",
    company: str = "",
    role: str = "",
    status: str = "unverified",
    verification_source: str = "",
) -> tuple[str, bool]:
    """Persist one contact. Only `verified` contacts may later be selected for a campaign."""
    normalized = email.strip().lower()
    if "@" not in normalized or len(normalized) > 320:
        raise ValueError("contact email is invalid")
    allowed = {"verified", "unverified", "suppressed", "opted_out", "bounced"}
    if status not in allowed:
        raise ValueError("contact status is invalid")
    with connection() as c:
        existing = c.execute("SELECT id FROM outreach_contacts WHERE email=?", (normalized,)).fetchone()
        if existing:
            c.execute(
                """UPDATE outreach_contacts SET full_name=?,company=?,role=?,status=?,verification_source=?,updated_at=?
                   WHERE id=?""",
                (full_name[:200], company[:200], role[:200], status, verification_source[:200], _now(), existing["id"]),
            )
            return str(existing["id"]), False
        contact_id = str(uuid.uuid4())
        c.execute(
            """INSERT INTO outreach_contacts(id,email,full_name,company,role,status,verification_source,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (contact_id, normalized, full_name[:200], company[:200], role[:200], status, verification_source[:200], _now(), _now()),
        )
        return contact_id, True


def get_outreach_contact(contact_id: str) -> dict[str, Any] | None:
    with connection() as c:
        row = c.execute(
            "SELECT id,email,full_name,company,role,status,verification_source FROM outreach_contacts WHERE id=?",
            (contact_id,),
        ).fetchone()
    return _row(row)


def get_verified_outreach_contacts(*, campaign_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Return eligible verified contacts not already assigned to the campaign."""
    with connection() as c:
        rows = c.execute(
            """SELECT c.id,c.email,c.full_name,c.company,c.role,c.status,c.verification_source
               FROM outreach_contacts c
               LEFT JOIN campaign_contact_attempts a ON a.contact_id=c.id AND a.campaign_id=?
               WHERE c.status='verified' AND a.contact_id IS NULL
               ORDER BY c.updated_at DESC LIMIT ?""",
            (campaign_id, max(1, min(limit, 100))),
        ).fetchall()
    return [dict(row) for row in rows]


def reserve_campaign_contact(campaign_id: str, contact_id: str, *, status: str = "queued", outbox_id: str | None = None) -> bool:
    """Reserve a contact once per campaign, preventing duplicate campaigns sends."""
    with connection() as c:
        try:
            c.execute(
                "INSERT INTO campaign_contact_attempts(campaign_id,contact_id,status,outbox_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (campaign_id, contact_id, status, outbox_id, _now(), _now()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def queue_action(
    campaign_id: str,
    action_type: str,
    payload: dict[str, Any],
    *,
    campaign_job_id: str | None = None,
    idempotency_key: str | None = None,
) -> tuple[str, bool]:
    """Create a durable action intent. Workers must enforce the Auditor before execution."""
    key = idempotency_key or hashlib.sha256(
        f"{campaign_id}|{campaign_job_id or ''}|{action_type}|{_json(payload)}".encode("utf-8")
    ).hexdigest()
    outbox_id = str(uuid.uuid4())
    with connection() as c:
        try:
            c.execute(
                "INSERT INTO action_outbox(id,campaign_id,campaign_job_id,action_type,idempotency_key,payload_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (outbox_id, campaign_id, campaign_job_id, action_type, key, _json(payload), "pending", _now(), _now()),
            )
            return outbox_id, True
        except sqlite3.IntegrityError:
            row = c.execute("SELECT id FROM action_outbox WHERE idempotency_key=?", (key,)).fetchone()
            return str(row["id"]), False


def claim_ready_actions(action_type: str, limit: int = 5) -> list[dict[str, Any]]:
    """Lease pending actions atomically. A worker must still validate before execution."""
    now = _now()
    with connection() as c:
        c.execute("BEGIN IMMEDIATE")
        rows = c.execute(
            """SELECT id,campaign_id,campaign_job_id,action_type,payload_json,attempts
               FROM action_outbox
               WHERE action_type=? AND status='pending' AND available_at<=?
               ORDER BY created_at ASC LIMIT ?""",
            (action_type, now, max(1, min(limit, 50))),
        ).fetchall()
        claimed: list[dict[str, Any]] = []
        for row in rows:
            changed = c.execute(
                "UPDATE action_outbox SET status='claimed',attempts=attempts+1,locked_at=?,updated_at=? WHERE id=? AND status='pending'",
                (now, now, row["id"]),
            ).rowcount
            if changed:
                item = dict(row)
                try:
                    item["payload"] = json.loads(item.pop("payload_json"))
                except json.JSONDecodeError:
                    item["payload"] = {}
                claimed.append(item)
    return claimed


def complete_action(action_id: str, *, error: str | None = None) -> None:
    with connection() as c:
        c.execute(
            "UPDATE action_outbox SET status='completed',completed_at=?,locked_at=NULL,last_error=?,updated_at=? WHERE id=?",
            (_now(), error, _now(), action_id),
        )


def block_action(action_id: str, reason: str) -> None:
    """Terminally block an unsafe action; it cannot silently retry as a send."""
    with connection() as c:
        c.execute(
            "UPDATE action_outbox SET status='blocked',locked_at=NULL,last_error=?,updated_at=? WHERE id=?",
            (reason[:1000], _now(), action_id),
        )


def mark_action_uncertain(action_id: str, reason: str) -> None:
    """Record unknown transport outcome without retrying and risking a duplicate send."""
    with connection() as c:
        c.execute(
            "UPDATE action_outbox SET status='uncertain',locked_at=NULL,last_error=?,updated_at=? WHERE id=?",
            (reason[:1000], _now(), action_id),
        )


def record_evidence(
    campaign_id: str,
    evidence_type: str,
    value: str,
    *,
    campaign_job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    if not get_campaign(campaign_id):
        raise ValueError("campaign_id is unknown")
    clean_type = _required_text(evidence_type, "evidence_type", 120)
    clean_value = _required_text(value, "evidence_value", 4000)
    if campaign_job_id:
        with connection() as c:
            linked = c.execute("SELECT 1 FROM campaign_jobs WHERE id=? AND campaign_id=?", (campaign_job_id, campaign_id)).fetchone()
        if linked is None:
            raise ValueError("campaign_job_id does not belong to campaign")
    evidence_id = str(uuid.uuid4())
    with connection() as c:
        c.execute(
            "INSERT INTO application_evidence(id,campaign_id,campaign_job_id,evidence_type,value,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (evidence_id, campaign_id, campaign_job_id, clean_type, clean_value, _json(metadata), _now()),
        )
    return evidence_id


def ensure_source_health(source: str, status: str = "configured") -> None:
    """Register a source without overwriting a probe-derived health state."""
    with connection() as c:
        c.execute(
            """INSERT OR IGNORE INTO source_health(source,status,successful_checks,failed_checks,last_error,last_checked_at,updated_at)
               VALUES(?,?,?,?,?,?,?)""",
            (source, status, 0, 0, None, None, _now()),
        )


def record_source_health(source: str, status: str, error: str | None = None) -> None:
    """Record a genuine probe result; configuration is not a failed health check."""
    success = 1 if status in {"healthy", "baseline", "stable"} else 0
    failure = 1 if status in {"blocked", "drifted", "unavailable", "degraded", "failed"} else 0
    with connection() as c:
        existing = c.execute("SELECT source FROM source_health WHERE source=?", (source,)).fetchone()
        if existing:
            c.execute(
                """UPDATE source_health SET status=?, successful_checks=successful_checks+?, failed_checks=failed_checks+?,
                   last_error=?, last_checked_at=?, updated_at=? WHERE source=?""",
                (status, success, failure, error, _now(), _now(), source),
            )
        else:
            c.execute(
                "INSERT INTO source_health(source,status,successful_checks,failed_checks,last_error,last_checked_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (source, status, success, failure, error, _now(), _now()),
            )


def latest_portal_probe(source: str) -> dict[str, Any] | None:
    with connection() as c:
        row = c.execute(
            """SELECT id,source,adapter_id,adapter_version,target_url,status,fingerprint,previous_fingerprint,
                      observation_json,error_code,observed_at
               FROM portal_probe_runs WHERE source=? ORDER BY observed_at DESC LIMIT 1""",
            (source,),
        ).fetchone()
    result = _row(row)
    if result:
        try:
            observation = json.loads(result.pop("observation_json", "{}"))
        except (TypeError, ValueError):
            observation = {}
        result["observation"] = observation if isinstance(observation, dict) else {}
    return result


def record_portal_probe(
    *,
    source: str,
    adapter_id: str,
    adapter_version: str,
    target_url: str,
    status: str,
    fingerprint: str = "",
    previous_fingerprint: str = "",
    observation: dict[str, Any] | None = None,
    error_code: str = "",
) -> str:
    """Persist sanitized read-only portal observation data; never application values."""
    allowed_statuses = {"baseline", "stable", "drifted", "blocked", "unavailable"}
    if status not in allowed_statuses:
        raise ValueError("portal probe status is invalid")
    probe_id = str(uuid.uuid4())
    with connection() as c:
        c.execute(
            """INSERT INTO portal_probe_runs(
                id,source,adapter_id,adapter_version,target_url,status,fingerprint,previous_fingerprint,
                observation_json,error_code,observed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                probe_id, source, adapter_id, adapter_version, target_url[:2000], status,
                fingerprint[:128] or None, previous_fingerprint[:128] or None,
                _json(observation), error_code[:200], _now(),
            ),
        )
    return probe_id


def select_portal_probe_target(source: str) -> dict[str, Any] | None:
    """Use an existing discovered public job URL; never invent or scrape new targets here."""
    with connection() as c:
        row = c.execute(
            """SELECT id,campaign_id,source,job_url FROM campaign_jobs
               WHERE source=? AND job_url LIKE 'https://%' ORDER BY updated_at DESC LIMIT 1""",
            (source,),
        ).fetchone()
    return _row(row)


def record_service_health(check_name: str, status: str, detail: str = "") -> None:
    with connection() as c:
        c.execute(
            "INSERT OR REPLACE INTO service_health(check_name,status,detail,checked_at) VALUES(?,?,?,?)",
            (check_name, status, detail[:1000], _now()),
        )


def health_snapshot() -> dict[str, Any]:
    with connection() as c:
        checks = c.execute("SELECT check_name,status,detail,checked_at FROM service_health ORDER BY check_name").fetchall()
        sources = c.execute("SELECT source,status,successful_checks,failed_checks,last_error,last_checked_at FROM source_health ORDER BY source").fetchall()
    return {"checks": [dict(r) for r in checks], "sources": [dict(r) for r in sources]}


def recover_stale_outbox(stale_after_seconds: int = 900) -> int:
    """Safe self-healing: release stuck claimed work. It never executes an action."""
    cutoff = _now() - max(60, stale_after_seconds)
    with connection() as c:
        cur = c.execute(
            "UPDATE action_outbox SET status='pending',locked_at=NULL,updated_at=?,last_error='worker lease expired; safely returned to queue' WHERE status='claimed' AND locked_at<?",
            (_now(), cutoff),
        )
        return cur.rowcount


def metrics() -> dict[str, Any]:
    with connection() as c:
        application_rows = c.execute("SELECT status, COUNT(*) AS count FROM applications GROUP BY status").fetchall()
        campaign_rows = c.execute("SELECT status, COUNT(*) AS count FROM campaigns GROUP BY status").fetchall()
        outbox_rows = c.execute("SELECT status, COUNT(*) AS count FROM action_outbox GROUP BY status").fetchall()
        dead_count = c.execute("SELECT COUNT(*) AS count FROM dead_letter").fetchone()["count"]
        last = c.execute("SELECT MAX(updated_at) AS last FROM applications WHERE status='submitted'").fetchone()["last"]
    by_status = {row["status"]: row["count"] for row in application_rows}
    total = sum(by_status.values())
    success = by_status.get("submitted", 0)
    return {
        "total": total,
        "by_status": by_status,
        "dead_letter": dead_count,
        "success_rate_pct": round(100.0 * success / total, 1) if total else 0.0,
        "last_submit_ts": last,
        "campaigns": {row["status"]: row["count"] for row in campaign_rows},
        "outbox": {row["status"]: row["count"] for row in outbox_rows},
    }


if __name__ == "__main__":
    initialize()
    print("DB init OK at", DB_PATH)
    print("metrics:", metrics())

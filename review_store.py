#!/usr/bin/env python3
"""Campaign-scoped durable storage for approval records.

Kept separate from ``db.py`` so the approval subsystem can be added without
rewriting the existing database module. Uses the same SQLite connection and
foreign-keyed campaign ledger.
"""
from __future__ import annotations

import json
import time
from typing import Any

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS application_reviews (
    campaign_id TEXT NOT NULL,
    source TEXT NOT NULL,
    posting_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    state TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (campaign_id, source, posting_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_application_reviews_campaign_state
ON application_reviews(campaign_id, state, updated_at DESC);
"""


def _ensure_schema() -> None:
    db.initialize()
    with db.connection() as c:
        c.executescript(SCHEMA)
        c.commit()


class CampaignReviewStore:
    def __init__(self, campaign_id: str) -> None:
        if not campaign_id:
            raise ValueError("campaign_id is required")
        self.campaign_id = campaign_id
        _ensure_schema()

    def list_records(self) -> list[dict[str, Any]]:
        with db.connection() as c:
            rows = c.execute(
                "SELECT record_json FROM application_reviews WHERE campaign_id=? ORDER BY updated_at DESC",
                (self.campaign_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                rec = json.loads(row["record_json"])
                if isinstance(rec, dict):
                    out.append(rec)
            except (TypeError, json.JSONDecodeError):
                continue
        return out

    def get_record(self, source: str, posting_id: str) -> dict[str, Any] | None:
        with db.connection() as c:
            row = c.execute(
                "SELECT record_json FROM application_reviews WHERE campaign_id=? AND source=? AND posting_id=?",
                (self.campaign_id, str(source), str(posting_id)),
            ).fetchone()
        if row is None:
            return None
        try:
            rec = json.loads(row["record_json"])
        except (TypeError, json.JSONDecodeError):
            return None
        return rec if isinstance(rec, dict) else None

    def save_record(self, rec: dict[str, Any]) -> None:
        source = str(rec.get("source") or "").strip()
        posting_id = str(rec.get("posting_id") or "").strip()
        state = str(rec.get("_state") or "").strip()
        if not source or not posting_id or not state:
            raise ValueError("review record requires source, posting_id and _state")
        stored = dict(rec)
        stored["_campaign_id"] = self.campaign_id
        with db.connection() as c:
            previous = c.execute(
                "SELECT state FROM application_reviews WHERE campaign_id=? AND source=? AND posting_id=?",
                (self.campaign_id, source, posting_id),
            ).fetchone()
            c.execute(
                """
                INSERT INTO application_reviews(campaign_id, source, posting_id, record_json, state, updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(campaign_id, source, posting_id) DO UPDATE SET
                    record_json=excluded.record_json,
                    state=excluded.state,
                    updated_at=excluded.updated_at
                """,
                (
                    self.campaign_id,
                    source,
                    posting_id,
                    json.dumps(stored, ensure_ascii=False, separators=(",", ":")),
                    state,
                    time.time(),
                ),
            )
            c.commit()
        old_state = previous["state"] if previous else None
        if old_state != state:
            db.add_campaign_event(
                self.campaign_id,
                "approval_state_changed",
                "info",
                f"Application review state changed from {old_state or 'new'} to {state}.",
                {
                    "source": source,
                    "posting_id": posting_id,
                    "state_before": old_state,
                    "state_after": state,
                    "approved_by": (stored.get("_draft") or {}).get("approved_by"),
                    "approval_digest": (stored.get("_draft") or {}).get("approval_digest"),
                },
            )


def seed_from_campaign_job(campaign_id: str, campaign_job: dict[str, Any]) -> dict[str, Any]:
    """Convert an existing campaign job row into the canonical review record once."""
    source = str(campaign_job.get("source") or "unknown")
    posting_id = str(campaign_job.get("id") or campaign_job.get("job_hash") or "")
    path_state = str(campaign_job.get("path_state") or "portal_complex")
    return {
        "source": source,
        "employer_key": str(campaign_job.get("company") or "").casefold().replace(" ", "-")[:120],
        "posting_id": posting_id,
        "company": str(campaign_job.get("company") or ""),
        "title": str(campaign_job.get("title") or ""),
        "location": str(campaign_job.get("location") or ""),
        "employment_type": "Unknown",
        "job_url": str(campaign_job.get("job_url") or ""),
        "apply_url": str(campaign_job.get("job_url") or ""),
        "description": str(campaign_job.get("description") or ""),
        "application_mode": "email" if path_state == "direct_email" else "portal",
        "required_fields": [],
        "_state": "path_verified" if path_state in {"direct_email", "portal_upload_verified"} else "needs_review",
        "_path": path_state,
        "_raw": {"campaign_job_id": campaign_job.get("id")},
        "_campaign_id": campaign_id,
    }


__all__ = ["CampaignReviewStore", "seed_from_campaign_job"]

#!/usr/bin/env python3
"""Offline end-to-end customer journey tests.

The suite uses a temporary SQLite database and never sends email, opens a browser,
submits an application, or calls an external service.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import db

ROOT = Path(__file__).resolve().parent


def expect_raises(fn, exc_type):
    try:
        fn()
    except exc_type:
        return True, None
    except Exception as exc:
        return False, f"wrong exception: {type(exc).__name__}: {exc}"
    return False, "no exception"


def run() -> dict[str, object]:
    original_db_path = db.DB_PATH
    with tempfile.TemporaryDirectory(prefix="autoapply-dry-run-") as temp_dir:
        db.DB_PATH = os.path.join(temp_dir, "test.db")
        db.initialize()
        checks: list[dict[str, object]] = []

        def check(case_id, description, expected, actual, detail=""):
            checks.append({
                "id": case_id,
                "description": description,
                "expected": expected,
                "actual": actual,
                "passed": expected == actual,
                "detail": detail,
            })

        # 1: valid campaign creates a private access token and intake event.
        campaign, token = db.create_campaign(
            candidate_name="Sarah Al-Ghamdi",
            candidate_email="sarah@example.com",
            target_role="Junior Software Engineer",
            city="Riyadh",
            industry="AI/Tech",
            seniority="Junior",
            language="English",
            cv_path="/tmp/sarah.pdf",
            cv_original_name="sarah.pdf",
            cv_sha256="a" * 64,
        )
        check("journey_01", "valid campaign intake", True, bool(campaign.get("id") and token))

        # 2: campaign access token authorizes its own records.
        check("journey_02", "correct campaign token authorizes access", True, db.campaign_authorized(campaign["id"], token))

        # 3: wrong token must not authorize.
        check("journey_03", "wrong token rejected", False, db.campaign_authorized(campaign["id"], "wrong-token"))

        # 4: missing email should be rejected at the database boundary.
        ok, detail = expect_raises(
            lambda: db.create_campaign(candidate_name="No Email", candidate_email="", target_role="Intern"),
            ValueError,
        )
        check("journey_04", "missing email rejected", True, ok, detail or "")

        # 5: malformed email should be rejected at the database boundary.
        ok, detail = expect_raises(
            lambda: db.create_campaign(candidate_name="Bad Email", candidate_email="not-an-email", target_role="Intern"),
            ValueError,
        )
        check("journey_05", "malformed email rejected", True, ok, detail or "")

        # 6: activation is read-only and records an event.
        active = db.activate_campaign(campaign["id"])
        check("journey_06", "campaign activation", "active_readonly", active.get("status"))

        # 7: invalid job URL should be rejected before discovery is stored.
        ok, detail = expect_raises(
            lambda: db.add_campaign_job(campaign["id"], company="Acme", title="Intern", job_url="not-a-url"),
            ValueError,
        )
        check("journey_07", "malformed job URL rejected", True, ok, detail or "")

        # 8: valid job is inserted once.
        job_id, inserted = db.add_campaign_job(
            campaign["id"], company="Acme", title="Junior Operations Analyst",
            job_url="https://jobs.example.com/acme/1", source="direct_sa", location="Riyadh, Saudi Arabia",
        )
        check("journey_08", "valid job inserted", True, bool(job_id and inserted))

        # 9: duplicate posting is idempotent.
        same_job_id, inserted_again = db.add_campaign_job(
            campaign["id"], company="Acme", title="Junior Operations Analyst",
            job_url="https://jobs.example.com/acme/1", source="direct_sa", location="Riyadh, Saudi Arabia",
        )
        check("journey_09", "duplicate job deduplicated", (job_id, False), (same_job_id, inserted_again))

        # 10: empty evidence must be rejected.
        ok, detail = expect_raises(lambda: db.record_evidence(campaign["id"], "confirmation_url", ""), ValueError)
        check("journey_10", "empty evidence rejected", True, ok, detail or "")

        # 11: valid evidence is stored and visible in the summary.
        evidence_id = db.record_evidence(
            campaign["id"], "confirmation_url", "https://jobs.example.com/acme/1/confirmation", campaign_job_id=job_id,
        )
        summary = db.campaign_summary(campaign["id"])
        check("journey_11", "valid evidence counted", True, bool(evidence_id and summary["evidence_count"] == 1))

        # 12: outbox action is idempotent.
        action_id, created = db.queue_action(campaign["id"], "portal_submit", {"job_id": job_id}, campaign_job_id=job_id, idempotency_key="idem-1")
        same_action_id, created_again = db.queue_action(campaign["id"], "portal_submit", {"job_id": job_id}, campaign_job_id=job_id, idempotency_key="idem-1")
        check("journey_12", "outbox duplicate prevented", (action_id, False), (same_action_id, created_again))

        # 13: opted-out contacts must not be offered to a campaign.
        opted_id, _ = db.upsert_outreach_contact(email="opted@example.com", status="opted_out")
        offered = db.get_verified_outreach_contacts(campaign_id=campaign["id"], limit=20)
        check("journey_13", "opted-out contact excluded", False, any(row["id"] == opted_id for row in offered))

        # 14: a verified contact can be reserved once and only once.
        verified_id, _ = db.upsert_outreach_contact(email="hr@example.com", status="verified", verification_source="dry-run")
        reserve_one = db.reserve_campaign_contact(campaign["id"], verified_id)
        reserve_two = db.reserve_campaign_contact(campaign["id"], verified_id)
        check("journey_14", "verified contact reservation is idempotent", (True, False), (reserve_one, reserve_two))

        report = {
            "mode": "offline_customer_journey_dry_run",
            "external_actions": False,
            "scenario_count": len(checks),
            "passed": sum(1 for row in checks if row["passed"]),
            "failed": sum(1 for row in checks if not row["passed"]),
            "checks": checks,
        }
        (ROOT / "customer_journey_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        db.DB_PATH = original_db_path
        return report


if __name__ == "__main__":
    run()

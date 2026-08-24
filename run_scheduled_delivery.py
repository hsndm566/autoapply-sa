"""Dispatch up to five eligible verified-contact applications per active client.

This runner is intended only for the GitHub Actions schedule. It ignores client 1,
never invents job evidence, skips already tracked recipients, and persists both
accepted and transport-uncertain outcomes to ``tracking.csv`` for the workflow to
commit after the run. It has no manual ``--execute`` switch: the scheduled
environment gate is the only path that enables transport.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import auditor
import db
import email_dispatcher
import run_verified_contact_warmup as shared
import send_applications as sender
from warmup_config import (
    SCHEDULED_DELIVERY_ENVIRONMENT_FLAG,
    SCHEDULED_DELIVERY_SCOPE,
    WARMUP_CLIENTS,
    WARMUP_EVIDENCE_TYPE,
    is_authorized_warmup_sender,
)

MAX_PER_IDENTITY_PER_RUN = 5
ACTIVE_CLIENT_IDS = frozenset(WARMUP_CLIENTS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", default="jobs.csv")
    parser.add_argument("--clients", default="clients.csv")
    parser.add_argument("--tracking", default="tracking.csv")
    parser.add_argument("--cvs-dir", default="cvs")
    return parser.parse_args()


def select_jobs(
    path: Path,
    tracked: set[str],
    deliverable_client_ids: frozenset[int] | set[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Select in source order, up to the per-client cap, only client 2/3 contacts."""
    deliverable_client_ids = set(ACTIVE_CLIENT_IDS if deliverable_client_ids is None else deliverable_client_ids)
    selected: list[dict[str, Any]] = []
    skipped = Counter()
    per_client = Counter()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"recipient_email", "company", "role", "city", "client_id", "evidence_type", "public_job_url"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"jobs file is missing scheduled-delivery columns: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            raw_client_id = str(row.get("client_id") or "").strip()
            if raw_client_id not in {str(client_id) for client_id in ACTIVE_CLIENT_IDS}:
                skipped["inactive_client"] += 1
                continue
            client_id = int(raw_client_id)
            if client_id not in deliverable_client_ids:
                skipped["client_cv_invalid"] += 1
                continue
            if per_client[client_id] >= MAX_PER_IDENTITY_PER_RUN:
                skipped["per_identity_cap"] += 1
                continue
            recipient_raw = str(row.get("recipient_email") or "").strip()
            company = str(row.get("company") or "").strip()
            role = str(row.get("role") or "").strip()
            try:
                recipient = sender.normalize_email(recipient_raw, "recipient_email")
            except ValueError:
                skipped["invalid_recipient"] += 1
                continue
            if recipient in tracked:
                skipped["tracked"] += 1
                continue
            if not company or not role:
                skipped["missing_company_or_role"] += 1
                continue
            if str(row.get("evidence_type") or "").strip() != WARMUP_EVIDENCE_TYPE:
                skipped["evidence_not_verified_contact"] += 1
                continue
            if str(row.get("public_job_url") or "").strip():
                skipped["public_job_url_not_blank"] += 1
                continue
            selected.append({
                "row_number": row_number,
                "recipient_email": recipient,
                "company": company,
                "role": role,
                "city": str(row.get("city") or "").strip(),
                "client_id": client_id,
            })
            per_client[client_id] += 1
    return selected, dict(skipped)


def deliverable_active_clients(
    clients: dict[int, dict[str, str]],
    cvs_dir: Path,
) -> tuple[frozenset[int], list[str]]:
    """Return active clients with one valid approved CV; exclude an invalid client as a whole."""
    deliverable: set[int] = set()
    blocked_clients: list[str] = []
    for client_id in ACTIVE_CLIENT_IDS:
        client = clients.get(client_id)
        if not client or not is_authorized_warmup_sender(client_id, str(client.get("sender_email") or "")):
            blocked_clients.append(f"client {client_id}: sender identity is not authorized for scheduled delivery")
            continue
        try:
            sender.read_valid_pdf(cvs_dir, client["cv_file"])
        except (FileNotFoundError, ValueError) as error:
            blocked_clients.append(f"client {client_id}: skipped because its CV is invalid ({error})")
            continue
        deliverable.add(client_id)
    return frozenset(deliverable), blocked_clients


def build_package(job: dict[str, Any], client: dict[str, str], cvs_dir: Path) -> dict[str, Any]:
    material = "|".join((SCHEDULED_DELIVERY_SCOPE, str(job["client_id"]), job["recipient_email"], job["company"], job["role"]))
    application_id = f"scheduled-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"
    return {
        "application_id": application_id,
        "job": {"company": job["company"], "role": job["role"], "url": "", "evidence_type": WARMUP_EVIDENCE_TYPE},
        "candidate": {
            "full_name": client["client_name"],
            "email": client["sender_email"],
            "cv_path": str((cvs_dir / client["cv_file"]).resolve()),
        },
        "destination": {
            "recipient": job["recipient_email"],
            "subject": f"Application — {job['role']}",
            "is_test_recipient": False,
            "evidence_type": WARMUP_EVIDENCE_TYPE,
        },
        "draft": sender.build_cover_letter(client["client_name"], job["company"], job["role"], job["city"]),
        "submission": {
            "channel": "email",
            "mode": "live",
            "cv_transport": "email_attachment",
            "client_id": job["client_id"],
            "sender_email": client["sender_email"],
            "evidence_type": WARMUP_EVIDENCE_TYPE,
            "warmup_scope": SCHEDULED_DELIVERY_SCOPE,
        },
    }


def preflight(jobs: list[dict[str, Any]], clients: dict[int, dict[str, str]], cvs_dir: Path) -> tuple[list[tuple[dict[str, Any], dict[str, str], dict[str, Any], auditor.AuditDecision]], list[str]]:
    blocked = shared.assert_runtime_ready(jobs, clients, cvs_dir)
    ready: list[tuple[dict[str, Any], dict[str, str], dict[str, Any], auditor.AuditDecision]] = []
    for job in jobs:
        client = clients[int(job["client_id"])]
        package = build_package(job, client, cvs_dir)
        decision = auditor.audit_application(package["application_id"], package, require_ai_review=False)
        if decision.approved:
            ready.append((job, client, package, decision))
        else:
            blocked.append(f"{job['recipient_email']}: {decision.summary}")
    return ready, blocked


def execute(ready: list[tuple[dict[str, Any], dict[str, str], dict[str, Any], auditor.AuditDecision]], tracking_path: Path, cvs_dir: Path) -> list[dict[str, Any]]:
    if os.environ.get("EMAIL_OUTREACH_ENABLED", "").casefold() != "true":
        raise RuntimeError("EMAIL_OUTREACH_ENABLED=true is required for scheduled delivery")
    if os.environ.get(SCHEDULED_DELIVERY_ENVIRONMENT_FLAG, "").casefold() != "true":
        raise RuntimeError(f"{SCHEDULED_DELIVERY_ENVIRONMENT_FLAG}=true is required for scheduled delivery")
    if not os.environ.get("BREVO_API_KEY", "").strip():
        raise RuntimeError("BREVO_API_KEY is required for scheduled delivery")

    campaign_ids: dict[int, str] = {}
    queued: list[tuple[dict[str, Any], dict[str, str], str]] = []
    for job, client, package, decision in ready:
        client_id = int(job["client_id"])
        if client_id not in ACTIVE_CLIENT_IDS or not is_authorized_warmup_sender(client_id, client["sender_email"]):
            raise RuntimeError(f"client {client_id} is not active for scheduled delivery")
        campaign_id = campaign_ids.setdefault(client_id, shared.create_client_campaign(client, cvs_dir))
        action_id, added = email_dispatcher.queue_audited_email_application(campaign_id, package, decision.approval_token)
        if not added:
            raise RuntimeError(f"existing action prevents a duplicate scheduled delivery for {job['recipient_email']}")
        queued.append((job, client, action_id))

    outcomes: list[dict[str, Any]] = []
    for index, (job, client, action_id) in enumerate(queued):
        action = db.claim_action(action_id, email_dispatcher.ACTION_TYPE)
        if action is None:
            raise RuntimeError(f"could not claim queued scheduled action for {job['recipient_email']}")
        result = email_dispatcher.dispatch_one(action)
        result.update({"recipient_email": job["recipient_email"], "client_id": job["client_id"], "sender_email": client["sender_email"]})
        outcomes.append(result)
        if result.get("status") == "accepted":
            shared.append_tracking(tracking_path, job["recipient_email"], client["sender_email"], f"scheduled-brevo-accepted:{result.get('transport_evidence') or ''}")
        elif result.get("status") == "uncertain":
            shared.append_tracking(tracking_path, job["recipient_email"], client["sender_email"], f"scheduled-transport-uncertain-suppressed:{result.get('reason') or 'unknown'}")
        if index < len(queued) - 1:
            time.sleep(sender.next_delay_seconds())
    return outcomes


def main() -> None:
    args = parse_args()
    clients = sender.load_clients(Path(args.clients))
    for client_id, expected in WARMUP_CLIENTS.items():
        client = clients.get(client_id, {})
        if client.get("sender_email") != expected["sender_email"] or client.get("client_name") != expected["client_name"]:
            raise ValueError(f"clients.csv does not match the authorized identity for client {client_id}")
    tracking_path, cvs_dir = Path(args.tracking), Path(args.cvs_dir)
    deliverable_client_ids, blocked_clients = deliverable_active_clients(clients, cvs_dir)
    selected, skipped = select_jobs(
        Path(args.jobs),
        sender.load_tracking(tracking_path),
        deliverable_client_ids,
    )
    ready, blocked = preflight(selected, clients, cvs_dir)
    print(json.dumps({
        "selected": len(selected),
        "ready": len(ready),
        "blocked_clients": blocked_clients,
        "blocked": blocked,
        "skipped": skipped,
    }, sort_keys=True))
    if blocked:
        raise SystemExit(2)
    if not ready:
        return
    outcomes = execute(ready, tracking_path, cvs_dir)
    print(json.dumps({"outcomes": outcomes}, sort_keys=True))


if __name__ == "__main__":
    main()

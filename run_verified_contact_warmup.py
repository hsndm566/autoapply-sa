"""Run the explicitly authorized, bounded verified-contact warm-up through the dispatcher.

Without ``--execute`` this validates the exact selected ten-row cohort and performs
no persistent queueing, network delivery, tracking update, or delay. With it, the
script queues fingerprint-bound Auditor approvals and delegates each message to the
only permitted dispatcher transport for this one-time scope.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import auditor
import db
import email_dispatcher
import send_applications as sender
from warmup_config import WARMUP_CLIENTS, WARMUP_EVIDENCE_TYPE, WARMUP_SCOPE, is_authorized_warmup_sender

MAX_PER_IDENTITY_PER_RUN = 5
TOTAL_LIMIT = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", default="jobs.csv")
    parser.add_argument("--clients", default="clients.csv")
    parser.add_argument("--tracking", default="tracking.csv")
    parser.add_argument("--cvs-dir", default="cvs")
    parser.add_argument("--execute", action="store_true", help="Queue and dispatch the already authorized one-time warm-up.")
    return parser.parse_args()


def load_selected_jobs(path: Path, tracked: set[str]) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"recipient_email", "company", "role", "city", "client_id", "evidence_type", "public_job_url"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"jobs file is missing required warm-up columns: {', '.join(sorted(missing))}")
        selected: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, start=2):
            raw_client_id = str(row.get("client_id") or "").strip()
            if raw_client_id not in {"2", "3"}:
                continue
            client_id = int(raw_client_id)
            recipient = sender.normalize_email(str(row.get("recipient_email") or ""), "recipient_email")
            company = str(row.get("company") or "").strip()
            role = str(row.get("role") or "").strip()
            if not company or not role:
                raise ValueError(f"warm-up row {row_number} is missing company or role")
            if recipient in tracked:
                raise ValueError(f"warm-up row {row_number} is already tracked: {recipient}")
            if str(row.get("evidence_type") or "").strip() != WARMUP_EVIDENCE_TYPE:
                raise ValueError(f"warm-up row {row_number} lacks verified-contact evidence")
            if str(row.get("public_job_url") or "").strip():
                raise ValueError(f"warm-up row {row_number} must not include a public-job URL in this authorized scope")
            selected.append({
                "row_number": row_number,
                "recipient_email": recipient,
                "company": company,
                "role": role,
                "city": str(row.get("city") or "").strip(),
                "client_id": client_id,
            })
    counts = Counter(job["client_id"] for job in selected)
    if len(selected) != TOTAL_LIMIT or counts != Counter({2: MAX_PER_IDENTITY_PER_RUN, 3: MAX_PER_IDENTITY_PER_RUN}):
        raise ValueError(f"warm-up scope must contain exactly five rows for each client, found {dict(counts)}")
    if len({job["recipient_email"] for job in selected}) != len(selected):
        raise ValueError("warm-up recipients must be unique")
    return selected


def assert_runtime_ready(jobs: list[dict[str, Any]], clients: dict[int, dict[str, str]], cvs_dir: Path) -> list[str]:
    blocked: list[str] = []
    for job in jobs:
        client_id = int(job["client_id"])
        client = clients.get(client_id)
        if not client or not is_authorized_warmup_sender(client_id, str(client.get("sender_email") or "")):
            blocked.append(f"{job['recipient_email']}: client sender is not authorized for the one-time scope")
            continue
        try:
            sender.read_valid_pdf(cvs_dir, client["cv_file"])
            if not sender.has_valid_mx(job["recipient_email"]):
                raise ValueError("recipient domain has no MX record")
        except (FileNotFoundError, ValueError) as error:
            blocked.append(f"{job['recipient_email']}: {error}")
    return blocked


def build_package(job: dict[str, Any], client: dict[str, str], cvs_dir: Path) -> dict[str, Any]:
    material = "|".join((WARMUP_SCOPE, str(job["client_id"]), job["recipient_email"], job["company"], job["role"]))
    application_id = f"warmup-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:24]}"
    return {
        "application_id": application_id,
        "job": {
            "company": job["company"],
            "role": job["role"],
            "url": "",
            "evidence_type": WARMUP_EVIDENCE_TYPE,
        },
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
            "warmup_scope": WARMUP_SCOPE,
        },
    }


def append_tracking(path: Path, recipient: str, sender_email: str, source_event: str) -> None:
    existing = sender.load_tracking(path)
    if recipient in existing:
        raise ValueError(f"tracking update refused for already tracked recipient: {recipient}")
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["recipient_email", "sent_at", "sender_used", "source_event"])
        if not file_exists or path.stat().st_size == 0:
            writer.writeheader()
        writer.writerow({
            "recipient_email": recipient,
            "sent_at": datetime.now(UTC).isoformat(),
            "sender_used": sender_email,
            "source_event": source_event,
        })


def create_client_campaign(client: dict[str, str], cvs_dir: Path) -> str:
    cv_path = (cvs_dir / client["cv_file"]).resolve()
    campaign, _token = db.create_campaign(
        candidate_name=client["client_name"],
        candidate_email=client["sender_email"],
        target_role="Verified-contact warm-up applications",
        cv_path=str(cv_path),
        cv_original_name=client["cv_file"],
        cv_sha256=auditor.cv_sha256(str(cv_path)),
    )
    return str(campaign["id"])


def preflight(jobs: list[dict[str, Any]], clients: dict[int, dict[str, str]], cvs_dir: Path) -> tuple[list[tuple[dict[str, Any], dict[str, str], dict[str, Any], auditor.AuditDecision]], list[str]]:
    blocked = assert_runtime_ready(jobs, clients, cvs_dir)
    if blocked:
        return [], blocked
    ready: list[tuple[dict[str, Any], dict[str, str], dict[str, Any], auditor.AuditDecision]] = []
    for job in jobs:
        client = clients[int(job["client_id"])]
        package = build_package(job, client, cvs_dir)
        decision = auditor.audit_application(package["application_id"], package, require_ai_review=False)
        if not decision.approved:
            blocked.append(f"{job['recipient_email']}: {decision.summary}")
            continue
        ready.append((job, client, package, decision))
    return ready, blocked


def execute(ready: list[tuple[dict[str, Any], dict[str, str], dict[str, Any], auditor.AuditDecision]], tracking_path: Path, cvs_dir: Path) -> list[dict[str, Any]]:
    if os.environ.get("EMAIL_OUTREACH_ENABLED", "").casefold() != "true":
        raise RuntimeError("EMAIL_OUTREACH_ENABLED=true is required for the explicitly authorized live warm-up")
    if os.environ.get("AUTOAPPLY_ONE_TIME_WARMUP", "").casefold() != "true":
        raise RuntimeError("AUTOAPPLY_ONE_TIME_WARMUP=true is required for the explicitly authorized live warm-up")
    if not os.environ.get("BREVO_API_KEY", "").strip():
        raise RuntimeError("BREVO_API_KEY is required for the explicitly authorized live warm-up")

    campaign_ids: dict[int, str] = {}
    queued: list[tuple[dict[str, Any], dict[str, str], str]] = []
    for job, client, package, decision in ready:
        client_id = int(job["client_id"])
        campaign_id = campaign_ids.setdefault(client_id, create_client_campaign(client, cvs_dir))
        action_id, added = email_dispatcher.queue_audited_email_application(campaign_id, package, decision.approval_token)
        if not added:
            raise RuntimeError(f"existing action prevents a duplicate warm-up send for {job['recipient_email']}")
        queued.append((job, client, action_id))

    outcomes: list[dict[str, Any]] = []
    for index, (job, client, action_id) in enumerate(queued):
        action = db.claim_action(action_id, email_dispatcher.ACTION_TYPE)
        if action is None:
            raise RuntimeError(f"could not claim queued warm-up action for {job['recipient_email']}")
        result = email_dispatcher.dispatch_one(action)
        result.update({"recipient_email": job["recipient_email"], "client_id": job["client_id"], "sender_email": client["sender_email"]})
        outcomes.append(result)
        if result.get("status") == "accepted":
            append_tracking(
                tracking_path,
                job["recipient_email"],
                client["sender_email"],
                f"warmup-brevo-accepted:{result.get('transport_evidence') or ''}",
            )
        elif result.get("status") == "uncertain":
            append_tracking(
                tracking_path,
                job["recipient_email"],
                client["sender_email"],
                f"warmup-transport-uncertain-suppressed:{result.get('reason') or 'unknown'}",
            )
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
    jobs = load_selected_jobs(Path(args.jobs), sender.load_tracking(tracking_path))
    ready, blocked = preflight(jobs, clients, cvs_dir)
    print(json.dumps({"selected": len(jobs), "ready": len(ready), "blocked": blocked, "execute": args.execute}, sort_keys=True))
    if blocked:
        raise SystemExit(2)
    if not args.execute:
        return
    outcomes = execute(ready, tracking_path, cvs_dir)
    print(json.dumps({"outcomes": outcomes}, sort_keys=True))


if __name__ == "__main__":
    main()

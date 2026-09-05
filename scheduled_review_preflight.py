#!/usr/bin/env python3
"""Scheduled preparation only.

Runs the existing verified-contact selection and Auditor preflight without
creating campaigns, queue actions, opening SMTP/Brevo transport, or mutating
tracking. Human-approved delivery must happen through the campaign review lane.
"""
from __future__ import annotations

import json
from pathlib import Path

import run_scheduled_delivery as scheduled
import send_applications as sender
from warmup_config import WARMUP_CLIENTS


def main() -> None:
    scheduled.initialize_glitchtip()
    args = scheduled.parse_args()
    clients = sender.load_clients(Path(args.clients))
    for client_id, expected in WARMUP_CLIENTS.items():
        client = clients.get(client_id, {})
        if client.get("sender_email") != expected["sender_email"] or client.get("client_name") != expected["client_name"]:
            raise ValueError(f"clients.csv does not match configured identity for client {client_id}")

    tracking_path = Path(args.tracking)
    cvs_dir = Path(args.cvs_dir)
    deliverable_client_ids, blocked_clients = scheduled.deliverable_active_clients(clients, cvs_dir)
    selected, skipped = scheduled.select_jobs(
        Path(args.jobs),
        sender.load_tracking(tracking_path),
        deliverable_client_ids,
    )
    ready, blocked = scheduled.preflight(selected, clients, cvs_dir)
    result = {
        "mode": "review_preflight_only",
        "selected": len(selected),
        "ready_for_human_review": len(ready),
        "blocked_clients": blocked_clients,
        "blocked": blocked,
        "skipped": skipped,
        "queued": 0,
        "sent": 0,
    }
    print(json.dumps(result, sort_keys=True))
    if blocked:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

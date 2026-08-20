"""Add prior uncertain one-time warm-up attempts to the do-not-contact ledger.

This is a suppression-only reconciliation. It never sends, queues, retries, or
asserts delivery. It prevents the transport-uncertain recipients from being
selected for a later run until a human reviews their outcome.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from warmup_config import WARMUP_SCOPE


def reconcile(db_path: Path, tracking_path: Path) -> int:
    with tracking_path.open(newline="", encoding="utf-8") as handle:
        tracked = {str(row.get("recipient_email") or "").strip().casefold() for row in csv.DictReader(handle)}
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT payload_json,last_error FROM action_outbox WHERE status='uncertain' AND action_type='audited_email_application'"
        ).fetchall()
    finally:
        connection.close()
    pending: list[tuple[str, str, str]] = []
    for payload_raw, last_error in rows:
        payload = json.loads(payload_raw)
        package = dict(payload.get("application_package") or {})
        submission = dict(package.get("submission") or {})
        destination = dict(package.get("destination") or {})
        if str(submission.get("warmup_scope") or "") != WARMUP_SCOPE:
            continue
        recipient = str(destination.get("recipient") or "").strip().casefold()
        sender = str(submission.get("sender_email") or "").strip().casefold()
        if recipient and sender and recipient not in tracked:
            pending.append((recipient, sender, str(last_error or "unknown")[:120]))
            tracked.add(recipient)
    if not pending:
        return 0
    with tracking_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["recipient_email", "sent_at", "sender_used", "source_event"])
        for recipient, sender, reason in pending:
            writer.writerow({
                "recipient_email": recipient,
                "sent_at": datetime.now(UTC).isoformat(),
                "sender_used": sender,
                "source_event": f"warmup-transport-uncertain-suppressed:{reason}",
            })
    return len(pending)


if __name__ == "__main__":
    print(reconcile(Path("autoapply.db"), Path("tracking.csv")))

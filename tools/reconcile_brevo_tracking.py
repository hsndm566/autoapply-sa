"""Seed tracking.csv from read-only Brevo event history.

Every external recipient observed in the supplied event file is tracked, including
errors and bounces. This is intentionally conservative: an attempted or failed
prior contact is not silently retried by the new sender.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


INTERNAL_RECIPIENTS = {"hasanadam506@gmail.com"}


def main() -> None:
    source_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    events = json.loads(source_path.read_text(encoding="utf-8")).get("events", [])
    records: dict[str, dict[str, str]] = {}
    for event in events:
        email = str(event.get("email") or "").strip().lower()
        if not email or "@" not in email or email in INTERNAL_RECIPIENTS or email.endswith("@hsndm.tech"):
            continue
        current = records.get(email)
        candidate = {
            "recipient_email": email,
            "sent_at": str(event.get("date") or ""),
            "sender_used": str(event.get("from") or "unknown"),
            "source_event": str(event.get("event") or "unknown"),
        }
        if current is None or candidate["sent_at"] > current["sent_at"]:
            records[email] = candidate

    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["recipient_email", "sent_at", "sender_used", "source_event"])
        writer.writeheader()
        writer.writerows(records[email] for email in sorted(records))
    print(f"Wrote {len(records)} conservative tracking records to {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: reconcile_brevo_tracking.py <events.json> <tracking.csv>")
    main()

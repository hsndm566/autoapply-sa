"""Convert a legacy recipient list into the reviewable jobs.csv schema.

The converter preserves only recipient email, company, and role from the supplied
CSV. It does not infer city, role, company, skills, experience, or job URLs.
Every converted row is assigned to client_id 1 for review.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()

    source_path = Path(args.source)
    destination_path = Path(args.destination)
    with source_path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        expected = {"recipient_email", "company", "role"}
        missing = expected.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Legacy CSV missing columns: {', '.join(sorted(missing))}")
        rows = []
        for row in reader:
            email = str(row.get("recipient_email") or "").strip().lower()
            if not email or "@" not in email:
                continue
            rows.append(
                {
                    "recipient_email": email,
                    "company": str(row.get("company") or "").strip(),
                    "role": str(row.get("role") or "").strip(),
                    "city": "",
                    "client_id": "1",
                }
            )

    with destination_path.open("w", newline="", encoding="utf-8") as destination_file:
        writer = csv.DictWriter(
            destination_file,
            fieldnames=["recipient_email", "company", "role", "city", "client_id"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Converted {len(rows)} rows to {destination_path}")


if __name__ == "__main__":
    main()

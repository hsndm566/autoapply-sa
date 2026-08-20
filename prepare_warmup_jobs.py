"""Create the bounded client 2/3 verified-contact warm-up jobs file from a supplied list.

This script never sends email. It selects only full, syntactically valid, untracked
company/role records in source order, assigns five rows to each approved client,
and retains every other source row as client 1.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from warmup_config import WARMUP_EVIDENCE_TYPE

EMAIL_RE = re.compile(r"^[^@,\s]+@[^@,\s]+\.[^@,\s]+$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="User-supplied verified CSV source")
    parser.add_argument("--tracking", default="tracking.csv")
    parser.add_argument("--output", default="jobs.csv")
    return parser.parse_args()


def _tracked_recipients(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            str(row.get("recipient_email") or "").strip().casefold()
            for row in csv.DictReader(handle)
            if str(row.get("recipient_email") or "").strip()
        }


def _complete_row(row: dict[str, str], tracked: set[str]) -> bool:
    recipient = str(row.get("recipient_email") or "").strip().casefold()
    return bool(
        EMAIL_RE.fullmatch(recipient)
        and recipient not in tracked
        and str(row.get("company") or "").strip()
        and str(row.get("role") or "").strip()
    )


def _saif_suitable(role: str) -> bool:
    value = role.casefold()
    return bool(
        re.search(r"customer service|admin(?:istration)?|operations", value)
        and not re.search(r"industrial|engineer|supply chain|quality", value)
    )


def _amro_suitable(role: str) -> bool:
    value = role.casefold()
    return bool(re.search(r"industrial engineering|industrial engineer|quality|supply chain", value))


def prepare(source: Path, tracking: Path, output: Path) -> dict[int, list[dict[str, str]]]:
    tracked = _tracked_recipients(tracking)
    with source.open(newline="", encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    required = {"recipient_email", "company", "role"}
    if not source_rows or not required.issubset(source_rows[0]):
        raise ValueError("The supplied list must contain recipient_email, company, and role columns")

    selected_indices: dict[int, list[int]] = {2: [], 3: []}
    for index, row in enumerate(source_rows):
        if len(selected_indices[2]) < 5 and _complete_row(row, tracked) and _saif_suitable(str(row.get("role") or "")):
            selected_indices[2].append(index)
            continue
        if len(selected_indices[3]) < 5 and _complete_row(row, tracked) and _amro_suitable(str(row.get("role") or "")):
            selected_indices[3].append(index)

    if len(selected_indices[2]) != 5 or len(selected_indices[3]) != 5:
        raise ValueError(f"Unable to select exactly five rows per client: { {client_id: len(rows) for client_id, rows in selected_indices.items()} }")

    selected_by_index = {index: client_id for client_id, indices in selected_indices.items() for index in indices}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["recipient_email", "company", "role", "city", "client_id", "evidence_type", "public_job_url"],
        )
        writer.writeheader()
        for index, row in enumerate(source_rows):
            client_id = selected_by_index.get(index, 1)
            writer.writerow({
                "recipient_email": str(row.get("recipient_email") or "").strip(),
                "company": str(row.get("company") or "").strip(),
                "role": str(row.get("role") or "").strip(),
                "city": str(row.get("city") or "").strip(),
                "client_id": client_id,
                "evidence_type": WARMUP_EVIDENCE_TYPE if client_id in {2, 3} else "",
                "public_job_url": "",
            })

    return {
        client_id: [source_rows[index] for index in indices]
        for client_id, indices in selected_indices.items()
    }


def main() -> None:
    args = parse_args()
    selected = prepare(Path(args.source), Path(args.tracking), Path(args.output))
    for client_id in (2, 3):
        print(f"client_id={client_id} selected={len(selected[client_id])}")
        for row in selected[client_id]:
            print(f"  {row['recipient_email']} | {row['company']} | {row['role']}")


if __name__ == "__main__":
    main()

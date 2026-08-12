"""Import recruiter-contact exports into the durable outreach contact store.

Importing contacts never queues or sends an email.  A contact is selectable only if
its source has explicitly marked it verified; invalid, duplicate, opted-out, and
suppressed records are retained or rejected safely as appropriate.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import db

_EMAIL_FIELDS = ("email", "email_address", "recruiter_email", "contact_email")
_NAME_FIELDS = ("full_name", "name", "recruiter_name", "contact_name")
_COMPANY_FIELDS = ("company", "employer", "organization")
_ROLE_FIELDS = ("role", "title", "job_title")
_STATUS_FIELDS = ("status", "verification_status")


def _value(row: dict[str, str], fields: tuple[str, ...]) -> str:
    normalized = {str(key).strip().lower(): str(value or "").strip() for key, value in row.items()}
    for field in fields:
        if normalized.get(field):
            return normalized[field]
    return ""


def import_contacts_csv(
    path: str | Path,
    *,
    verification_source: str,
    mark_verified: bool = False,
) -> dict[str, Any]:
    """Import a CSV export and return only aggregate counts.

    ``mark_verified`` defaults to false to prevent a malformed or unreviewed export
    from becoming eligible for delivery.  Use it only for an already verified list,
    recording the provenance in ``verification_source``.
    """
    source = verification_source.strip()
    if not source:
        raise ValueError("verification_source is required")
    source_path = Path(path).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    counts = {"rows": 0, "inserted": 0, "updated": 0, "invalid": 0, "verified": 0, "unverified": 0}
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("contact CSV is missing headers")
        for row in reader:
            counts["rows"] += 1
            email = _value(row, _EMAIL_FIELDS)
            if not email:
                counts["invalid"] += 1
                continue
            supplied_status = _value(row, _STATUS_FIELDS).lower()
            if supplied_status in {"opted_out", "suppressed", "bounced"}:
                status = supplied_status
            else:
                status = "verified" if mark_verified else "unverified"
            try:
                _id, created = db.upsert_outreach_contact(
                    email=email,
                    full_name=_value(row, _NAME_FIELDS),
                    company=_value(row, _COMPANY_FIELDS),
                    role=_value(row, _ROLE_FIELDS),
                    status=status,
                    verification_source=source,
                )
            except ValueError:
                counts["invalid"] += 1
                continue
            counts["inserted" if created else "updated"] += 1
            if status == "verified":
                counts["verified"] += 1
            else:
                counts["unverified"] += 1
    return counts


__all__ = ["import_contacts_csv"]

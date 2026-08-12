"""Import recruiter-contact exports into the durable outreach contact store.

Importing contacts never queues or sends an email. A contact is selectable only if
its source has explicitly marked it verified; invalid, duplicate, opted-out, and
suppressed records are retained or rejected safely as appropriate.
"""
from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import db

_EMAIL_FIELDS = ("email", "email_address", "recruiter_email", "contact_email")
_NAME_FIELDS = ("full_name", "name", "recruiter_name", "contact_name")
_COMPANY_FIELDS = ("company", "employer", "organization")
_ROLE_FIELDS = ("role", "title", "job_title")
_STATUS_FIELDS = ("status", "verification_status")


def _value(row: Mapping[str, Any], fields: tuple[str, ...]) -> str:
    normalized = {str(key).strip().lower(): str(value or "").strip() for key, value in row.items()}
    for field in fields:
        if normalized.get(field):
            return normalized[field]
    return ""


def import_contact_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    verification_source: str,
    mark_verified: bool = False,
) -> dict[str, int]:
    """Import contact mappings and return only aggregate counts.

    ``mark_verified`` defaults to false to prevent an unreviewed export from
    becoming eligible for delivery. Its use records the provenance supplied in
    ``verification_source``. Suppression statuses in the input always override the
    verified flag.
    """
    source = verification_source.strip()
    if not source:
        raise ValueError("verification_source is required")
    counts = {"rows": 0, "inserted": 0, "updated": 0, "invalid": 0, "verified": 0, "unverified": 0}
    for row in rows:
        counts["rows"] += 1
        if not isinstance(row, Mapping):
            counts["invalid"] += 1
            continue
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


def import_contacts_csv(
    path: str | Path,
    *,
    verification_source: str,
    mark_verified: bool = False,
) -> dict[str, int]:
    """Import a CSV export using common recruiter-contact header aliases."""
    source_path = Path(path).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("contact CSV is missing headers")
        return import_contact_rows(reader, verification_source=verification_source, mark_verified=mark_verified)


__all__ = ["import_contact_rows", "import_contacts_csv"]

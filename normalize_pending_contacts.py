#!/usr/bin/env python3
"""Normalize the audited pending-contact CSV without changing its data semantics."""
from __future__ import annotations

import csv
from pathlib import Path

SOURCE = Path("email_outreach_pending_after_audit_2026-08-13.csv")
TARGET = Path("email_outreach_pending.csv")

with SOURCE.open(newline="", encoding="utf-8") as source:
    reader = csv.DictReader(source)
    fields = list(reader.fieldnames or [])
    rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
with TARGET.open("w", newline="", encoding="utf-8") as target:
    writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
print(f"normalized_rows={len(rows)} target={TARGET}")

"""Prepare a bounded email-application batch without sending any message.

This module validates the CV artifact and email-contact structure, ranks suitable
contacts from the audited pending list, and writes only preparation metadata. It
never opens an SMTP connection, queues an outbox send, or invokes external APIs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import db

BASE = Path(__file__).resolve().parent
DEFAULT_SOURCE = BASE / "email_outreach_pending.csv"
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
RELEVANCE_TERMS = (
    "industrial", "logistics", "warehouse", "supply", "operations", "procurement",
    "manufacturing", "engineering", "construction", "quality", "safety", "project",
)


def _cv_metadata(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"CV artifact missing: {path}")
    if path.suffix.casefold() != ".pdf":
        raise ValueError("CV artifact must be a PDF")
    content = path.read_bytes()
    if len(content) < 1024:
        raise ValueError("CV artifact is unexpectedly small")
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def _active_campaign_cv() -> tuple[Path, str]:
    """Resolve the most recently updated active-readonly campaign CV on the deployed worker."""
    campaigns = db.list_campaigns_with_status("active_readonly", limit=20)
    if not campaigns:
        raise RuntimeError("no active_readonly campaign CV is available for preparation")
    campaign = max(campaigns, key=lambda item: float(item.get("updated_at") or 0))
    return Path(str(campaign.get("cv_path") or "")), str(campaign.get("id") or "")


def _priority(row: dict[str, str]) -> tuple[int, int, str]:
    haystack = " ".join(row.get(key, "") for key in ("company", "title", "location")).casefold()
    matches = sum(term in haystack for term in RELEVANCE_TERMS)
    generic_penalty = int(row.get("email", "").casefold().startswith(("info@", "care@")))
    return (-matches, generic_penalty, row.get("company", "").casefold())


def prepare_pending_batch(*, limit: int = 10, source: Path = DEFAULT_SOURCE, cv_path: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    """Return and persist a bounded, non-sending preparation list."""
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"pending contact list missing: {source}")
    campaign_id = ""
    if cv_path is not None:
        candidate_cv = Path(cv_path)
    elif os.environ.get("CANDIDATE_CV_PATH"):
        candidate_cv = Path(str(os.environ["CANDIDATE_CV_PATH"]))
    else:
        candidate_cv, campaign_id = _active_campaign_cv()
    output_path = output or Path(os.environ.get("EMAIL_PREPARATION_OUTPUT", "/data/autoapply/email_preparation_batch.json"))
    cv = _cv_metadata(candidate_cv)
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    valid = [
        row for row in rows
        if row.get("status") == "new" and EMAIL_RE.match(str(row.get("email", "")).strip())
    ]
    selected = sorted(valid, key=_priority)[:limit]
    result: dict[str, Any] = {
        "ok": True,
        "mode": "preparation_only",
        "submits_applications": False,
        "sends_email": False,
        "prepared_at": time.time(),
        "cv": cv,
        "campaign_id": campaign_id,
        "source_rows": len(rows),
        "valid_contacts": len(valid),
        "selected_count": len(selected),
        "candidates": [
            {
                "lead_id": row.get("lead_id"),
                "company": row.get("company"),
                "title": row.get("title"),
                "location": row.get("location"),
                "email": row.get("email"),
                "required_before_send": [
                    "current_contact_verification",
                    "job_or_role_specific_factual_draft",
                    "independent_auditor_approval",
                    "reputation_gate_clear",
                    "CV_attachment_recheck",
                ],
            }
            for row in selected
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(output_path, 0o600)
    return result


__all__ = ["prepare_pending_batch"]

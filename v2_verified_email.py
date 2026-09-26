"""Bridge V2 verified jobs to the existing verified-contact + Auditor email lane.

This module never discovers or guesses an email address. It exposes email delivery only
when an existing outreach_contacts row is currently verified, belongs to the exact
normalized employer, and has verified source evidence. Delivery then goes through the
existing Auditor and email_dispatcher boundaries.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Callable, Mapping

import auditor
import db
import email_dispatcher


class V2VerifiedEmailError(RuntimeError):
    def __init__(self, reason: str, status: int = 409) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def verified_contact_for_company(company: str) -> dict[str, Any] | None:
    """Return the newest exact-company verified contact with verified evidence.

    Matching is intentionally strict. A missing/ambiguous match disables email rather
    than risking delivery to an unrelated employer.
    """
    target = _company_key(company)
    if not target:
        return None

    with db.connection() as connection:
        rows = connection.execute(
            """
            SELECT
              c.id,c.email,c.full_name,c.company,c.role,c.status,c.verification_source,
              e.source AS evidence_source,e.observed_at
            FROM outreach_contacts c
            JOIN outreach_contact_source_evidence e ON e.contact_id=c.id
            WHERE c.status='verified' AND e.status='verified'
            ORDER BY e.observed_at DESC,c.updated_at DESC
            """
        ).fetchall()

    matches = [dict(row) for row in rows if _company_key(str(row["company"] or "")) == target]
    if not matches:
        return None

    contact = matches[0]
    email = str(contact.get("email") or "").strip().casefold()
    source = str(contact.get("evidence_source") or contact.get("verification_source") or "").strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or not source:
        return None
    return {
        "id": str(contact["id"]),
        "email": email,
        "full_name": str(contact.get("full_name") or ""),
        "company": str(contact.get("company") or ""),
        "role": str(contact.get("role") or ""),
        "verification_source": source,
        "observed_at": float(contact.get("observed_at") or 0),
    }


def email_capability(company: str) -> dict[str, Any]:
    """Expose only capability, never the verified contact itself, to V2 clients."""
    return {"emailEligible": verified_contact_for_company(company) is not None}


def _persist_exact_pdf(cv_bytes: bytes, original_name: str, user_id: str, job_id: str) -> Path:
    if not original_name.lower().endswith(".pdf"):
        raise V2VerifiedEmailError("email-cv-pdf-required", 409)
    if not cv_bytes.startswith(b"%PDF-") or b"%%EOF" not in cv_bytes[-4096:]:
        raise V2VerifiedEmailError("email-cv-pdf-invalid", 409)

    root = Path(os.environ.get("CV_STORAGE_DIR", Path(db.BASE_DIR) / "data" / "cv")) / "v2"
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(cv_bytes).hexdigest()
    token = hashlib.sha256(f"{user_id}:{job_id}:{digest}".encode("utf-8")).hexdigest()[:28]
    path = root / f"v2-{token}.pdf"
    if path.exists() and path.read_bytes() != cv_bytes:
        raise V2VerifiedEmailError("email-cv-cache-conflict", 500)
    if not path.exists():
        path.write_bytes(cv_bytes)
    return path


def dispatch_v2_application(
    *,
    user_id: str,
    candidate_email: str,
    candidate_name: str,
    job: Mapping[str, Any],
    contact: Mapping[str, Any],
    cv_bytes: bytes,
    cv_name: str,
    draft: str,
    v2_application_id: str,
    accounting_check: Callable[[], bool],
    ai_reviewer: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit, queue, reserve, and synchronously dispatch one V2 email application."""
    contact_id = str(contact.get("id") or "").strip()
    recipient = str(contact.get("email") or "").strip().casefold()
    if not contact_id or not recipient:
        raise V2VerifiedEmailError("verified-recipient-required", 409)

    current = verified_contact_for_company(str(job.get("company") or ""))
    if not current or current["id"] != contact_id or current["email"] != recipient:
        raise V2VerifiedEmailError("verified-recipient-stale", 409)

    cv_path = _persist_exact_pdf(cv_bytes, cv_name, user_id, str(job.get("id") or ""))
    campaign, _access_token = db.create_campaign(
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        target_role=str(job.get("title") or ""),
        city=str(job.get("location") or ""),
        industry="",
        seniority="",
        language="",
        cv_path=str(cv_path),
        cv_original_name=cv_name,
        cv_sha256=auditor.cv_sha256(str(cv_path)),
    )
    campaign_id = str(campaign.get("id") or "")
    if not campaign_id:
        raise V2VerifiedEmailError("audited-email-campaign-failed", 502)

    application_id = f"v2-{v2_application_id}"
    package = {
        "application_id": application_id,
        "job": {
            "company": str(job.get("company") or ""),
            "role": str(job.get("title") or ""),
            "url": str(job.get("canonicalUrl") or ""),
        },
        "candidate": {
            "full_name": candidate_name,
            "email": candidate_email,
            "cv_path": str(cv_path),
            "cv_text": "",
        },
        "draft": draft,
        "destination": {
            "recipient": recipient,
            "subject": f"{candidate_name} for {str(job.get('title') or '')}",
            "is_test_recipient": False,
        },
        "submission": {
            "channel": "email",
            "mode": "live",
            "cv_transport": "email_attachment",
            "delivery_provider": "brevo",
            "accounting_mode": "v2_supabase",
            "v2_application_id": v2_application_id,
        },
    }

    reviewer = ai_reviewer or auditor.configured_ai_reviewer
    decision = auditor.audit_application(
        application_id,
        package,
        ai_reviewer=reviewer,
        require_ai_review=True,
    )
    if not decision.approved:
        raise V2VerifiedEmailError("auditor-rejected-application", 409)

    outbox_id, added = email_dispatcher.queue_audited_email_application(
        campaign_id,
        package,
        decision.approval_token,
    )
    if not added:
        raise V2VerifiedEmailError("duplicate-audited-email-intent", 409)
    if not db.reserve_campaign_contact(campaign_id, contact_id, outbox_id=outbox_id):
        db.block_action(outbox_id, "CAMPAIGN_CONTACT_ALREADY_RESERVED")
        raise V2VerifiedEmailError("verified-recipient-reservation-failed", 409)

    action = db.claim_action(outbox_id, email_dispatcher.ACTION_TYPE)
    if not action:
        raise V2VerifiedEmailError("audited-email-claim-failed", 502)

    result = email_dispatcher.dispatch_one(
        action,
        accounting_reservation_fn=lambda package: bool(
            str(dict(package.get("submission") or {}).get("v2_application_id") or "") == v2_application_id
            and accounting_check()
        ),
    )
    status = str(result.get("status") or "")
    if status == "accepted":
        return result
    if status == "uncertain":
        raise V2VerifiedEmailError("email-delivery-uncertain", 502)
    reason = str(result.get("reason") or "audited-email-blocked")
    raise V2VerifiedEmailError(reason, 409)


__all__ = [
    "V2VerifiedEmailError",
    "dispatch_v2_application",
    "email_capability",
    "verified_contact_for_company",
]

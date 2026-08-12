"""Prepare individualized campaign email intents for verified outreach contacts.

This bridge does not write copy or send mail. A caller supplies one tailored draft
for an explicit campaign, recruiter contact, and job context. The immutable package
is then approved by the independent Auditor before it can enter the email outbox.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import auditor
import db
import email_dispatcher


def _campaign_package(
    campaign: Mapping[str, Any],
    contact: Mapping[str, Any],
    *,
    application_id: str,
    job: Mapping[str, Any],
    draft: str,
    subject: str,
) -> dict[str, Any]:
    company = str(job.get("company") or contact.get("company") or "").strip()
    role = str(job.get("role") or job.get("title") or campaign.get("target_role") or "").strip()
    job_url = str(job.get("url") or job.get("job_url") or "").strip()
    if not (company and role and job_url):
        raise ValueError("job company, role, and HTTPS URL are required")
    return {
        "application_id": application_id,
        "job": {"company": company, "role": role, "url": job_url},
        "candidate": {
            "full_name": str(campaign.get("candidate_name") or ""),
            "email": str(campaign.get("candidate_email") or ""),
            "cv_path": str(campaign.get("cv_path") or ""),
            "cv_text": "",  # candidate facts may be added by an approved drafting stage; never infer them here.
        },
        "draft": draft,
        "destination": {
            "recipient": str(contact.get("email") or ""),
            "subject": subject,
            "is_test_recipient": False,
        },
        "submission": {"channel": "email", "mode": "live", "cv_transport": "email_attachment"},
    }


def prepare_audited_campaign_email(
    campaign_id: str,
    contact_id: str,
    *,
    application_id: str,
    job: Mapping[str, Any],
    draft: str,
    subject: str = "",
    ai_reviewer: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    require_ai_review: bool = True,
) -> dict[str, Any]:
    """Audit and queue one campaign email for a single verified contact.

    The caller must provide the tailored draft; this method neither generates nor
    repairs application language. Any missing evidence, invalid CV, unavailable AI
    review, unverified contact, or repeated campaign-contact pair is a stop.
    """
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise ValueError("campaign not found")
    contact = db.get_outreach_contact(contact_id)
    if not contact or contact.get("status") != "verified":
        raise PermissionError("only verified contacts may receive campaign application email")
    package = _campaign_package(
        campaign,
        contact,
        application_id=application_id,
        job=job,
        draft=draft,
        subject=subject,
    )
    reviewer = ai_reviewer or auditor.configured_ai_reviewer
    decision = auditor.audit_application(
        application_id,
        package,
        ai_reviewer=reviewer,
        require_ai_review=require_ai_review,
    )
    if not decision.approved:
        db.add_campaign_event(
            campaign_id,
            "email_application_audit_rejected",
            "warning",
            "Campaign email was not queued because the Auditor rejected its application package.",
            {"contact_id": contact_id, "application_id": application_id, "findings": [finding.code for finding in decision.findings]},
        )
        return {"queued": False, "audit_status": decision.status, "findings": [finding.code for finding in decision.findings]}
    outbox_id, added = email_dispatcher.queue_audited_email_application(
        campaign_id,
        package,
        decision.approval_token,
    )
    if not added:
        return {"queued": False, "audit_status": decision.status, "reason": "duplicate_application_intent", "outbox_id": outbox_id}
    # Reserve only after a successful, idempotent queue insert. A duplicate reserve
    # forces the action terminally blocked rather than sending a second email.
    if not db.reserve_campaign_contact(campaign_id, contact_id, outbox_id=outbox_id):
        db.block_action(outbox_id, "CAMPAIGN_CONTACT_ALREADY_RESERVED")
        return {"queued": False, "audit_status": decision.status, "reason": "campaign_contact_already_reserved", "outbox_id": outbox_id}
    db.add_campaign_event(
        campaign_id,
        "email_application_queued",
        "info",
        "An Auditor-approved CV-attached application email was queued for controlled delivery.",
        {"contact_id": contact_id, "application_id": application_id, "outbox_id": outbox_id},
    )
    return {"queued": True, "audit_status": decision.status, "outbox_id": outbox_id, "contact_id": contact_id}


__all__ = ["prepare_audited_campaign_email"]

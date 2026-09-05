#!/usr/bin/env python3
"""Controlled runtime for one persisted human-approved application.

The runtime reloads the canonical approval record from the campaign ledger and
rechecks the shared gate. Portal records invoke one source adapter immediately.
Direct-email records are re-audited and queued into the durable email dispatcher;
provider transport later repeats the human + Auditor checks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import campaign_email
import db
from review_store import CampaignReviewStore
from submit_gate import SubmissionRefused, guard


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _candidate_data(campaign: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    full_name = str(campaign.get("candidate_name") or "").strip()
    names = full_name.split(None, 1)
    first_name = names[0] if names else ""
    last_name = names[1] if len(names) > 1 else ""
    draft = dict(rec.get("_draft") or {})
    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": str(campaign.get("candidate_email") or "").strip(),
        "phone": "",
        "cv_path": str(campaign.get("cv_path") or "").strip(),
        "cName": full_name,
        "cEmail": str(campaign.get("candidate_email") or "").strip(),
        "cPhoneNumber": "",
        "cCoverLetter": str(draft.get("cover_letter") or ""),
    }


def _adapter(source: str) -> Callable[..., dict[str, Any]]:
    source = str(source or "").strip().casefold()
    if source == "greenhouse":
        from greenhouse_submit import submit_greenhouse

        return submit_greenhouse
    if source == "lever":
        from lever_submit import submit_lever

        return submit_lever
    if source == "ashby":
        from ashby_submit import submit_ashby

        return submit_ashby
    raise ValueError(f"no approved portal submit adapter for source {source!r}")


def _hold_after_nonfinal_result(
    store: CampaignReviewStore,
    rec: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    status = str(result.get("status") or "failed")
    reason = str(result.get("reason") or result.get("note") or status)[:300]
    held = dict(rec)
    held["_state"] = "needs_review"
    held["_review"] = {
        "reason": (
            "manual_challenge" if status == "manual_handoff"
            else "submission_uncertain" if status == "uncertain"
            else "submission_blocked"
        ),
        "detail": reason,
        "at": _now(),
    }
    held.pop("_submission_intent", None)
    store.save_record(held)
    return held


def _queue_direct_email(
    store: CampaignReviewStore,
    campaign_id: str,
    rec: dict[str, Any],
) -> dict[str, Any]:
    raw = dict(rec.get("_raw") or {})
    draft = dict(rec.get("_draft") or {})
    contact_id = str(raw.get("contact_id") or "").strip()
    if not contact_id:
        raise PermissionError("approved email record has no verified contact binding")
    application_id = str(raw.get("application_id") or rec.get("posting_id") or "").strip()
    if not application_id:
        raise ValueError("approved email record has no application id")

    result = campaign_email.prepare_audited_campaign_email(
        campaign_id,
        contact_id,
        application_id=application_id,
        job={
            "company": str(rec.get("company") or ""),
            "role": str(rec.get("title") or ""),
            "url": str(rec.get("job_url") or ""),
        },
        draft=str(draft.get("cover_letter") or ""),
        subject=str(draft.get("subject") or ""),
        human_approval_record=rec,
        campaign_job_id=str(raw.get("campaign_job_id") or "") or None,
    )
    if result.get("queued") is True:
        queued = dict(rec)
        queued["_submission_intent"] = {
            "channel": "email",
            "outbox_id": result.get("outbox_id"),
            "queued_at": _now(),
        }
        store.save_record(queued)
        return {
            "status": "queued_for_delivery",
            "source": "email",
            "posting_id": str(rec.get("posting_id") or ""),
            "outbox_id": result.get("outbox_id"),
        }

    if result.get("reason") == "duplicate_application_intent" and result.get("outbox_id"):
        queued = dict(rec)
        queued["_submission_intent"] = {
            "channel": "email",
            "outbox_id": result.get("outbox_id"),
            "queued_at": _now(),
            "deduplicated": True,
        }
        store.save_record(queued)
        return {
            "status": "queued_for_delivery",
            "source": "email",
            "posting_id": str(rec.get("posting_id") or ""),
            "outbox_id": result.get("outbox_id"),
            "deduplicated": True,
        }

    held = dict(rec)
    held["_state"] = "needs_review"
    held["_review"] = {
        "reason": "email_audit_rejected",
        "detail": result.get("findings") or result.get("reason") or "email queue rejected",
        "at": _now(),
    }
    store.save_record(held)
    return {
        "status": "needs_review",
        "hold_reason": "email_audit_rejected",
        "detail": held["_review"]["detail"],
    }


def submit_approved(campaign_id: str, source: str, posting_id: str) -> dict[str, Any]:
    """Execute the explicit submit action for one persisted approved record."""
    store = CampaignReviewStore(campaign_id)
    rec = store.get_record(source, posting_id)
    if rec is None:
        raise LookupError(f"no review record for {source}|{posting_id}")
    if str(rec.get("_campaign_id") or "") != str(campaign_id):
        raise PermissionError("review record belongs to a different campaign")

    guard(rec)
    if rec.get("_submission_intent"):
        raise SubmissionRefused("submission already queued", rec)

    path = str(rec.get("_path") or "")
    if path == "direct_email":
        return _queue_direct_email(store, campaign_id, rec)
    if path != "portal_upload_verified":
        raise PermissionError("review record is not approved for an executable submission path")

    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise LookupError("campaign not found")
    candidate = _candidate_data(campaign, rec)
    if not candidate["first_name"] or not candidate["email"] or not candidate["cv_path"]:
        raise ValueError("campaign is missing candidate name, email or CV required for submission")

    adapter = _adapter(source)
    result = adapter(rec, candidate)
    if not isinstance(result, dict):
        raise RuntimeError("submit adapter returned an invalid result")

    submitted = result.get("record")
    if result.get("submitted") is True and isinstance(submitted, dict):
        if submitted.get("_state") != "submitted_verified":
            raise RuntimeError("adapter claimed success without submitted_verified state")
        store.save_record(submitted)
        evidence = dict(result.get("evidence") or {})
        campaign_job_id = str((submitted.get("_raw") or {}).get("campaign_job_id") or "") or None
        db.record_evidence(
            campaign_id,
            f"portal_{str(source).casefold()}_submitted",
            str(evidence.get("confirmation_id") or evidence.get("confirmation_url") or evidence.get("success_marker") or "verified"),
            campaign_job_id=campaign_job_id,
            metadata={
                "source": str(source).casefold(),
                "approval_digest": str((submitted.get("_draft") or {}).get("approval_digest") or ""),
                "evidence_keys": sorted(evidence),
            },
        )
        db.add_campaign_event(
            campaign_id,
            "portal_submission_verified",
            "info",
            "A human-approved portal application was submitted and verification evidence was persisted.",
            {
                "source": str(source).casefold(),
                "posting_id": str(posting_id),
                "campaign_job_id": campaign_job_id,
                "evidence_keys": sorted(evidence),
            },
        )
        return {
            "status": "submitted_verified",
            "source": str(source).casefold(),
            "posting_id": str(posting_id),
            "evidence": evidence,
        }

    held = _hold_after_nonfinal_result(store, rec, result)
    db.add_campaign_event(
        campaign_id,
        "portal_submission_held",
        "warning",
        "Portal submission did not reach a verified terminal success state and was held for human review.",
        {
            "source": str(source).casefold(),
            "posting_id": str(posting_id),
            "status": str(result.get("status") or "failed"),
            "reason": str(result.get("reason") or result.get("note") or "")[:300],
        },
    )
    return {
        "status": held["_state"],
        "hold_reason": (held.get("_review") or {}).get("reason"),
        "detail": (held.get("_review") or {}).get("detail"),
    }


__all__ = ["submit_approved"]

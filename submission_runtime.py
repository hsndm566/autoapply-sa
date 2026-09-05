#!/usr/bin/env python3
"""One controlled runtime for submitting a persisted human-approved record.

This module is the bridge between the review API and source-specific portal
adapters. It never approves work. It loads the canonical record from the
campaign review store, rechecks the shared gate, invokes exactly one approved
adapter, and persists the verified result back to the same campaign ledger.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import db
from review_store import CampaignReviewStore
from submit_gate import SubmissionRefused, guard


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _candidate_data(campaign: dict[str, Any], rec: dict[str, Any]) -> dict[str, Any]:
    """Build factual adapter input only from persisted campaign data."""
    full_name = str(campaign.get("candidate_name") or "").strip()
    names = full_name.split(None, 1)
    first_name = names[0] if names else ""
    last_name = names[1] if len(names) > 1 else ""
    draft = dict(rec.get("_draft") or {})
    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": str(campaign.get("candidate_email") or "").strip(),
        "phone": "",  # The campaign schema has no phone field; never invent one.
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
    """Prevent automatic retry after a challenge or uncertain final click."""
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
    store.save_record(held)
    return held


def submit_approved(campaign_id: str, source: str, posting_id: str) -> dict[str, Any]:
    """Submit exactly one persisted approved portal record.

    The campaign access check lives at the HTTP boundary. This function assumes
    the caller has already authenticated to that campaign, but it still verifies
    the record is bound to the same campaign before any adapter can run.
    """
    store = CampaignReviewStore(campaign_id)
    rec = store.get_record(source, posting_id)
    if rec is None:
        raise LookupError(f"no review record for {source}|{posting_id}")
    if str(rec.get("_campaign_id") or "") != str(campaign_id):
        raise PermissionError("review record belongs to a different campaign")

    # This catches unapproved, forged, tampered and duplicate records before an
    # adapter can open a browser or make an employer-facing request.
    guard(rec)
    if rec.get("_path") != "portal_upload_verified":
        raise PermissionError("review record is not approved for portal submission")

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

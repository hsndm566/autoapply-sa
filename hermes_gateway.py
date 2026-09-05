"""Authenticated Hermes-to-backend draft gateway.

Hermes may research and propose draft email opportunities, but it has no send or
approval operation. Every verified opportunity is persisted into the campaign's
human review ledger and requires the grounded drafting stage before approval.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import auditor
import db
from review_store import CampaignReviewStore

GATEWAY_HEADER = "X-Hermes-Gateway-Token"
MAX_BATCH = 10
REQUIRED_SENDER = "apply@hsndm.tech"


def authorized(token: str) -> bool:
    expected = os.environ.get("HERMES_GATEWAY_TOKEN", "").strip()
    return bool(expected and token and hmac.compare_digest(token, expected))


def _text(value: Any, limit: int = 3000) -> str:
    return str(value or "").strip()[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _https_url(value: Any, field: str) -> str:
    url = _text(value, 2000)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be an HTTPS URL")
    return url


def _application_id(campaign_id: str, item: Mapping[str, Any]) -> str:
    supplied = _text(item.get("application_id"), 160)
    if supplied:
        return supplied
    material = "|".join((_text(item.get("company"), 200), _text(item.get("role"), 200), _text(item.get("job_url"), 2000), _text(item.get("recipient"), 320)))
    return "hermes-" + hashlib.sha256(f"{campaign_id}|{material}".encode()).hexdigest()[:32]


def _package(campaign: Mapping[str, Any], item: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    company = _text(item.get("company"), 200)
    role = _text(item.get("role"), 200)
    recipient = _text(item.get("recipient"), 320).lower()
    subject = _text(item.get("subject"), 500)
    draft = _text(item.get("draft"), 2500)
    job_url = _https_url(item.get("job_url"), "job_url")
    source_url = _https_url(item.get("source_url"), "source_url")
    verification = _text(item.get("contact_verification"), 120)
    language = _text(item.get("language"), 40).lower() or "english"
    if not company or not role or not recipient or "@" not in recipient or not subject or not draft:
        raise ValueError("company, role, recipient, subject, and draft are required")
    if verification != "verified_public_listing":
        raise ValueError("contact_verification must be verified_public_listing")
    if not item.get("contact_email_matches_source") is True:
        raise ValueError("contact_email_matches_source must be true")
    cv_path = _text(campaign.get("cv_path"), 1000)
    if not cv_path.lower().endswith(".pdf"):
        raise ValueError("campaign must have a PDF CV")
    application_id = _application_id(str(campaign["id"]), item)
    package = {
        "application_id": application_id,
        "job": {"company": company, "role": role, "url": job_url},
        "candidate": {
            "full_name": _text(campaign.get("candidate_name"), 200),
            "email": _text(campaign.get("candidate_email"), 320),
            "cv_path": cv_path,
            "cv_text": _text(item.get("candidate_facts"), 3000),
        },
        "draft": draft,
        "destination": {
            "recipient": recipient,
            "subject": subject,
            "is_test_recipient": False,
        },
        "submission": {
            "channel": "email",
            "mode": "preview",
            "cv_transport": "email_attachment",
            "sender": REQUIRED_SENDER,
            "language": language,
            "source_url": source_url,
        },
    }
    return package, source_url


def _persist_review_opportunity(
    campaign_id: str,
    package: Mapping[str, Any],
    *,
    contact_id: str,
    source_url: str,
    auditor_approved: bool,
    findings: list[str],
) -> None:
    """Place the external draft in review, never directly in an approvable state.

    Hermes copy has not passed ``draft_review.build_draft`` grounding. Keeping it
    in ``needs_review`` means a human can see the proposal but must run the
    campaign's grounded draft endpoint before ``approve_draft`` can succeed.
    """
    job = dict(package.get("job") or {})
    destination = dict(package.get("destination") or {})
    submission = dict(package.get("submission") or {})
    rec = {
        "source": "email",
        "employer_key": str(job.get("company") or "").casefold().replace(" ", "-")[:120],
        "posting_id": str(package.get("application_id") or ""),
        "company": str(job.get("company") or ""),
        "title": str(job.get("role") or ""),
        "location": "",
        "employment_type": "Unknown",
        "job_url": str(job.get("url") or ""),
        "apply_url": str(job.get("url") or ""),
        "description": "",
        "application_mode": "email",
        "required_fields": [],
        "_state": "needs_review",
        "_path": "direct_email",
        "_campaign_id": campaign_id,
        "_draft": {
            "lang": str(submission.get("language") or "en"),
            "match_score": None,
            "subject": str(destination.get("subject") or ""),
            "cover_letter": str(package.get("draft") or ""),
            "evidence": [],
            "gaps": [],
            "cv_highlights": [],
            "flagged_claims": ["external_draft_not_grounded"],
            "drafted_at": _now(),
            "approved_by": None,
            "approved_at": None,
        },
        "_review": {
            "reason": "external_draft_requires_grounded_redraft" if auditor_approved else "auditor_rejected_external_draft",
            "detail": findings,
            "at": _now(),
        },
        "_raw": {
            "contact_id": contact_id,
            "recipient": str(destination.get("recipient") or ""),
            "source_url": source_url,
            "application_id": str(package.get("application_id") or ""),
        },
    }
    CampaignReviewStore(campaign_id).save_record(rec)


def prepare_batch(campaign_id: str, items: Any) -> dict[str, Any]:
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        raise ValueError("campaign_id is required")
    if not isinstance(items, list) or not items:
        raise ValueError("applications must be a non-empty list")
    if len(items) > MAX_BATCH:
        raise ValueError(f"maximum draft batch is {MAX_BATCH}")
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise ValueError("campaign not found")
    results: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            results.append({"index": index, "status": "blocked", "reason": "application must be an object"})
            continue
        try:
            package, source_url = _package(campaign, item)
            contact_id, _created = db.upsert_outreach_contact(
                email=package["destination"]["recipient"],
                full_name=_text(item.get("contact_name"), 200),
                company=package["job"]["company"],
                role=package["job"]["role"],
                status="verified",
                verification_source=source_url,
            )
            decision = auditor.audit_application(package["application_id"], package)
            findings = [finding.code for finding in decision.findings]
            _persist_review_opportunity(
                campaign_id,
                package,
                contact_id=contact_id,
                source_url=source_url,
                auditor_approved=decision.approved,
                findings=findings,
            )
            result = {
                "index": index,
                "application_id": package["application_id"],
                "company": package["job"]["company"],
                "role": package["job"]["role"],
                "recipient": package["destination"]["recipient"],
                "language": package["submission"]["language"],
                "sender": REQUIRED_SENDER,
                "cv_path": package["candidate"]["cv_path"],
                "source_url": source_url,
                "contact_id": contact_id,
                "status": "draft_ready" if decision.approved else "blocked",
                "review_state": "needs_review",
                "audit_status": decision.status,
                "findings": findings,
                "queued": False,
                "sent": False,
            }
            results.append(result)
        except Exception as exc:
            results.append({"index": index, "status": "blocked", "reason": type(exc).__name__ + ": " + str(exc)[:300], "queued": False, "sent": False})
    return {"ok": True, "mode": "draft_only", "sender": REQUIRED_SENDER, "count": len(results), "results": results}


__all__ = ["GATEWAY_HEADER", "MAX_BATCH", "REQUIRED_SENDER", "authorized", "prepare_batch"]

"""Authenticated Hermes-to-backend draft gateway.

Hermes may research and draft, but it must submit packages here for validation.
This gateway deliberately has no send operation. It only persists verified contacts,
runs the Auditor, and returns draft-only review results.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import auditor
import db

GATEWAY_HEADER = "X-Hermes-Gateway-Token"
MAX_BATCH = 10
REQUIRED_SENDER = "apply@hsndm.tech"


def authorized(token: str) -> bool:
    expected = os.environ.get("HERMES_GATEWAY_TOKEN", "").strip()
    return bool(expected and token and hmac.compare_digest(token, expected))


def _text(value: Any, limit: int = 3000) -> str:
    return str(value or "").strip()[:limit]


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
                "audit_status": decision.status,
                "findings": [finding.code for finding in decision.findings],
                "queued": False,
                "sent": False,
            }
            results.append(result)
        except Exception as exc:
            results.append({"index": index, "status": "blocked", "reason": type(exc).__name__ + ": " + str(exc)[:300], "queued": False, "sent": False})
    return {"ok": True, "mode": "draft_only", "sender": REQUIRED_SENDER, "count": len(results), "results": results}


__all__ = ["GATEWAY_HEADER", "MAX_BATCH", "REQUIRED_SENDER", "authorized", "prepare_batch"]

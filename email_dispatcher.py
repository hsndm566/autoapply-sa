"""Audited employer-email dispatcher with explicit human approval.

The existing Auditor checks, PDF validation, idempotent outbox and SMTP/Brevo
proof remain in place. Human approval is an additional mandatory boundary.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, Mapping

import auditor
import db
from review_store import CampaignReviewStore
from submit_gate import SubmissionRefused, guard, mark_submitted
from warmup_config import (
    SCHEDULED_DELIVERY_ENVIRONMENT_FLAG,
    SCHEDULED_DELIVERY_SCOPE,
    WARMUP_CLIENTS,
    WARMUP_ENVIRONMENT_FLAG,
    WARMUP_EVIDENCE_TYPE,
    WARMUP_SCOPE,
)

ACTION_TYPE = "audited_email_application"
REQUIRED_APPLICATION_SENDER = "apply@hsndm.tech"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
BREVO_SMTP_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _enabled() -> bool:
    return os.environ.get("EMAIL_OUTREACH_ENABLED", "false").lower() == "true"


def _sender() -> str:
    return os.environ.get("GMAIL_USER", "").strip()


def _password() -> str:
    return os.environ.get("GMAIL_APP_PASSWORD", "").strip()


def _brevo_api_key() -> str:
    return os.environ.get("BREVO_API_KEY", "").strip()


def _warmup_enabled() -> bool:
    return os.environ.get(WARMUP_ENVIRONMENT_FLAG, "false").strip().lower() == "true"


def _scheduled_delivery_enabled() -> bool:
    return os.environ.get(SCHEDULED_DELIVERY_ENVIRONMENT_FLAG, "false").strip().lower() == "true"


def _authorized_brevo_sender(package: Mapping[str, Any]) -> str:
    submission = dict(package.get("submission") or {})
    job = dict(package.get("job") or {})
    candidate = dict(package.get("candidate") or {})
    try:
        client_id = int(submission.get("client_id"))
    except (TypeError, ValueError):
        return ""
    expected = WARMUP_CLIENTS.get(client_id, {})
    sender = str(submission.get("sender_email") or "").strip().lower()
    if not expected:
        return ""
    scope = str(submission.get("warmup_scope") or "")
    allowed_scope = (scope == WARMUP_SCOPE and _warmup_enabled()) or (
        scope == SCHEDULED_DELIVERY_SCOPE and _scheduled_delivery_enabled()
    )
    if not allowed_scope:
        return ""
    if str(submission.get("evidence_type") or "") != WARMUP_EVIDENCE_TYPE:
        return ""
    if str(job.get("evidence_type") or "") != WARMUP_EVIDENCE_TYPE or str(job.get("url") or "").strip():
        return ""
    if sender != str(expected["sender_email"]).casefold() or str(candidate.get("full_name") or "") != str(expected["client_name"]):
        return ""
    return sender


def _message_evidence(message: EmailMessage) -> str:
    material = "\n".join([
        str(message.get("From", "")),
        str(message.get("To", "")),
        str(message.get("Subject", "")),
        ",".join(str(part.get_filename() or "") for part in message.iter_attachments()),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _assert_pdf_attachment(message: EmailMessage) -> None:
    attachments = list(message.iter_attachments())
    if len(attachments) != 1:
        raise PermissionError("EMAIL_CV_ATTACHMENT_MISSING_OR_DUPLICATE")
    attachment = attachments[0]
    if attachment.get_content_type() != "application/pdf":
        raise PermissionError("EMAIL_CV_ATTACHMENT_NOT_PDF")
    payload = attachment.get_payload(decode=True) or b""
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-4096:]:
        raise PermissionError("EMAIL_CV_ATTACHMENT_INVALID_PDF")
    if not attachment.get_filename() or not attachment.get_filename().lower().endswith(".pdf"):
        raise PermissionError("EMAIL_CV_ATTACHMENT_FILENAME_INVALID")


def _assert_review_matches_package(review_record: Mapping[str, Any], package: Mapping[str, Any]) -> None:
    """Bind a human approval to the exact content about to be transmitted."""
    if str(review_record.get("_path") or "") != "direct_email":
        raise PermissionError("HUMAN_APPROVAL_NOT_FOR_EMAIL")
    draft = dict(review_record.get("_draft") or {})
    destination = dict(package.get("destination") or {})
    job = dict(package.get("job") or {})
    if str(draft.get("cover_letter") or "").strip() != str(package.get("draft") or "").strip():
        raise PermissionError("HUMAN_APPROVAL_DRAFT_MISMATCH")
    if str(draft.get("subject") or "").strip() != str(destination.get("subject") or "").strip():
        raise PermissionError("HUMAN_APPROVAL_SUBJECT_MISMATCH")
    approved_company = str(review_record.get("company") or "").strip()
    approved_title = str(review_record.get("title") or "").strip()
    package_company = str(job.get("company") or "").strip()
    package_title = str(job.get("role") or job.get("title") or "").strip()
    if approved_company and package_company and approved_company != package_company:
        raise PermissionError("HUMAN_APPROVAL_COMPANY_MISMATCH")
    if approved_title and package_title and approved_title != package_title:
        raise PermissionError("HUMAN_APPROVAL_ROLE_MISMATCH")


def _smtp_send(message: EmailMessage, sender: str, app_password: str) -> str:
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(sender, app_password)
        client.send_message(message, from_addr=sender, to_addrs=[str(message["To"])])
    return str(message.get("Message-ID", ""))


def _brevo_send(message: EmailMessage, sender: str, api_key: str) -> str:
    import requests

    attachment = list(message.iter_attachments())[0]
    payload = attachment.get_payload(decode=True) or b""
    request_body = {
        "sender": {"email": sender},
        "to": [{"email": str(message["To"])}],
        "subject": str(message["Subject"]),
        "textContent": message.get_body(preferencelist=("plain",)).get_content(),
        "attachment": [{
            "name": str(attachment.get_filename()),
            "content": base64.b64encode(payload).decode("ascii"),
        }],
    }
    response = requests.post(
        BREVO_SMTP_ENDPOINT,
        headers={"accept": "application/json", "api-key": api_key, "content-type": "application/json"},
        data=json.dumps(request_body),
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    message_id = str(result.get("messageId") or "").strip()
    if not message_id:
        raise RuntimeError("Brevo accepted the request without a message ID")
    return message_id


def queue_audited_email_application(
    campaign_id: str,
    application_package: Mapping[str, Any],
    auditor_approval_token: str,
    *,
    campaign_job_id: str | None = None,
    human_approval_record: Mapping[str, Any] | None = None,
) -> tuple[str, bool]:
    """Queue an email intent; transport remains impossible without human approval."""
    application_id = str(application_package.get("application_id") or "").strip()
    if not application_id:
        raise ValueError("application_package.application_id is required")
    submission = dict(application_package.get("submission") or {})
    if submission.get("channel") != "email" or submission.get("cv_transport") != "email_attachment":
        raise ValueError("email outbox accepts only email_attachment application packages")
    auditor.assert_execution_allowed(application_id, application_package, auditor_approval_token)

    approval: dict[str, Any] | None = None
    if human_approval_record is not None:
        approval = dict(human_approval_record)
        guard(approval)
        bound_campaign = str(approval.get("_campaign_id") or "")
        if bound_campaign and bound_campaign != campaign_id:
            raise PermissionError("human approval belongs to a different campaign")
        _assert_review_matches_package(approval, application_package)

    payload = {
        "application_package": application_package,
        "auditor_approval_token": auditor_approval_token,
        "human_approval_record": approval,
    }
    return db.queue_action(
        campaign_id,
        ACTION_TYPE,
        payload,
        campaign_job_id=campaign_job_id,
        idempotency_key=f"{campaign_id}:{application_id}:{auditor.application_fingerprint(application_package)}",
    )


def _block(action: Mapping[str, Any], reason: str) -> dict[str, Any]:
    db.block_action(str(action["id"]), reason)
    db.add_campaign_event(
        str(action["campaign_id"]),
        "email_delivery_blocked",
        "warning",
        "Employer email delivery was blocked before send.",
        {"outbox_id": action["id"], "reason": reason[:300]},
    )
    return {"outbox_id": action["id"], "status": "blocked", "reason": reason}


def dispatch_one(
    action: Mapping[str, Any], *,
    send_fn: Callable[[EmailMessage, str, str], str] = _smtp_send,
    brevo_send_fn: Callable[[EmailMessage, str, str], str] = _brevo_send,
) -> dict[str, Any]:
    payload = dict(action.get("payload") or {})
    package = payload.get("application_package")
    approval_token = str(payload.get("auditor_approval_token") or "")
    review_record = payload.get("human_approval_record")
    if not isinstance(package, Mapping):
        return _block(action, "OUTBOX_PACKAGE_INVALID")
    if not isinstance(review_record, Mapping):
        return _block(action, "HUMAN_APPROVAL_REQUIRED")

    review_record = dict(review_record)
    if str(review_record.get("_campaign_id") or action.get("campaign_id") or "") != str(action.get("campaign_id") or ""):
        return _block(action, "HUMAN_APPROVAL_CAMPAIGN_MISMATCH")
    try:
        guard(review_record)
        _assert_review_matches_package(review_record, package)
    except (SubmissionRefused, PermissionError) as exc:
        reason = exc.reason if isinstance(exc, SubmissionRefused) else str(exc)
        return _block(action, f"HUMAN_APPROVAL_INVALID: {reason}")

    if not _enabled():
        return _block(action, "EMAIL_OUTREACH_DISABLED")
    warmup_sender = _authorized_brevo_sender(package)
    transport = "brevo" if warmup_sender else "smtp"
    sender, credential = (warmup_sender, _brevo_api_key()) if warmup_sender else (_sender(), _password())
    if not sender or not credential:
        return _block(action, "BREVO_CREDENTIALS_UNAVAILABLE" if transport == "brevo" else "GMAIL_CREDENTIALS_UNAVAILABLE")
    if transport == "smtp" and sender.casefold() != REQUIRED_APPLICATION_SENDER:
        return _block(action, "SENDER_NOT_ALLOWED")

    try:
        application_id = str(package.get("application_id") or "")
        message = auditor.build_approved_email(package, sender, approval_token)
        _assert_pdf_attachment(message)
        transport_evidence = (
            brevo_send_fn(message, sender, credential)
            if transport == "brevo"
            else send_fn(message, sender, credential)
        )
    except PermissionError as exc:
        return _block(action, f"AUDITOR_RECHECK_FAILED: {exc}")
    except Exception as exc:
        db.mark_action_uncertain(str(action["id"]), f"transport_failed:{type(exc).__name__}")
        db.add_campaign_event(
            str(action["campaign_id"]),
            "email_delivery_uncertain",
            "warning",
            "Email transport failed; delivery was not recorded as successful.",
            {"outbox_id": action["id"], "error_type": type(exc).__name__},
        )
        return {"outbox_id": action["id"], "status": "uncertain", "reason": type(exc).__name__}

    evidence = _message_evidence(message)
    proof = {"transport_evidence": transport_evidence, "message_digest": evidence}
    try:
        submitted_record = mark_submitted(review_record, evidence=proof, channel="email")
        CampaignReviewStore(str(action["campaign_id"])).save_record(submitted_record)
    except Exception as exc:
        db.mark_action_uncertain(str(action["id"]), f"proof_persist_failed:{type(exc).__name__}")
        return {"outbox_id": action["id"], "status": "uncertain", "reason": "submission_proof_persist_failed"}

    db.complete_action(str(action["id"]))
    db.record_evidence(
        str(action["campaign_id"]),
        "email_brevo_accepted" if transport == "brevo" else "email_smtp_accepted",
        transport_evidence or evidence,
        campaign_job_id=str(action.get("campaign_job_id") or "") or None,
        metadata={"message_digest": evidence, "attachment_count": len(list(message.iter_attachments()))},
    )
    db.add_campaign_event(
        str(action["campaign_id"]),
        "email_delivery_accepted",
        "info",
        "Provider accepted a human-approved, Auditor-approved CV-attached application email.",
        {"outbox_id": action["id"], "message_digest": evidence, "transport": transport},
    )
    return {
        "outbox_id": action["id"],
        "status": "accepted",
        "evidence": evidence,
        "transport": transport,
        "transport_evidence": transport_evidence,
    }


def dispatch_pending(
    *, limit: int = 5,
    send_fn: Callable[[EmailMessage, str, str], str] = _smtp_send,
    brevo_send_fn: Callable[[EmailMessage, str, str], str] = _brevo_send,
) -> dict[str, Any]:
    if not _enabled():
        return {"enabled": False, "claimed": 0, "results": []}
    if not ((_sender() and _password()) or _brevo_api_key()):
        return {"enabled": True, "configuration": "incomplete", "claimed": 0, "results": []}
    actions = db.claim_ready_actions(ACTION_TYPE, limit=limit)
    results = [dispatch_one(action, send_fn=send_fn, brevo_send_fn=brevo_send_fn) for action in actions]
    return {"enabled": True, "claimed": len(actions), "results": results}


__all__ = [
    "ACTION_TYPE", "REQUIRED_APPLICATION_SENDER", "dispatch_pending", "dispatch_one",
    "queue_audited_email_application",
]

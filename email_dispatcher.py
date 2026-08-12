"""Audited Gmail outreach dispatcher for durable campaign outbox actions.

This module has no contact scraping or drafting logic.  It accepts only an already
queued, immutable application package and an Auditor approval token.  It validates
the approval immediately before building the MIME message, then delivers through
Gmail SMTP only when explicitly enabled by deployment configuration.
"""
from __future__ import annotations

import hashlib
import os
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, Mapping

import auditor
import db

ACTION_TYPE = "audited_email_application"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _enabled() -> bool:
    return os.environ.get("EMAIL_OUTREACH_ENABLED", "false").lower() == "true"


def _sender() -> str:
    return os.environ.get("GMAIL_USER", "").strip()


def _password() -> str:
    return os.environ.get("GMAIL_APP_PASSWORD", "").strip()


def _message_evidence(message: EmailMessage) -> str:
    """Return a digest for durable evidence; never persist message content or CV bytes."""
    material = "\n".join([
        str(message.get("From", "")), str(message.get("To", "")), str(message.get("Subject", "")),
        ",".join(str(part.get_filename() or "") for part in message.iter_attachments()),
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _smtp_send(message: EmailMessage, sender: str, app_password: str) -> str:
    """Send via authenticated TLS and return the SMTP Message-ID evidence value."""
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(sender, app_password)
        client.send_message(message, from_addr=sender, to_addrs=[str(message["To"])])
    return str(message.get("Message-ID", ""))


def queue_audited_email_application(
    campaign_id: str,
    application_package: Mapping[str, Any],
    auditor_approval_token: str,
    *,
    campaign_job_id: str | None = None,
) -> tuple[str, bool]:
    """Queue one immutable email intent after proving an Audit approval exists.

    The dispatcher will repeat this check immediately before delivery. This first
    check prevents a caller from accumulating obviously unauthorised send intents.
    """
    application_id = str(application_package.get("application_id") or "").strip()
    if not application_id:
        raise ValueError("application_package.application_id is required")
    submission = dict(application_package.get("submission") or {})
    if submission.get("channel") != "email" or submission.get("cv_transport") != "email_attachment":
        raise ValueError("email outbox accepts only email_attachment application packages")
    auditor.assert_execution_allowed(application_id, application_package, auditor_approval_token)
    payload = {
        "application_package": application_package,
        "auditor_approval_token": auditor_approval_token,
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
        "Audited email delivery was blocked before send.",
        {"outbox_id": action["id"], "reason": reason[:300]},
    )
    return {"outbox_id": action["id"], "status": "blocked", "reason": reason}


def dispatch_one(action: Mapping[str, Any], *, send_fn: Callable[[EmailMessage, str, str], str] = _smtp_send) -> dict[str, Any]:
    """Perform one email delivery only after a boundary audit recheck.

    Errors before calling ``send_fn`` are terminally blocked. Errors from the
    transport return the lease to the safe recovery flow rather than asserting a
    false delivery outcome.
    """
    payload = dict(action.get("payload") or {})
    package = payload.get("application_package")
    approval_token = str(payload.get("auditor_approval_token") or "")
    if not isinstance(package, Mapping):
        return _block(action, "OUTBOX_PACKAGE_INVALID")
    if not _enabled():
        return _block(action, "EMAIL_OUTREACH_DISABLED")
    sender, password = _sender(), _password()
    if not sender or not password:
        return _block(action, "GMAIL_CREDENTIALS_UNAVAILABLE")
    try:
        application_id = str(package.get("application_id") or "")
        message = auditor.build_approved_email(package, sender, approval_token)
        # `build_approved_email` rechecks a current, matching Auditor decision.
        transport_evidence = send_fn(message, sender, password)
    except PermissionError as exc:
        return _block(action, f"AUDITOR_RECHECK_FAILED: {exc}")
    except Exception as exc:
        # This state is terminal until human review: SMTP may have failed before or
        # after accepting the message, so automatic retry could create a duplicate.
        db.mark_action_uncertain(str(action["id"]), f"transport_failed:{type(exc).__name__}")
        db.add_campaign_event(
            str(action["campaign_id"]),
            "email_delivery_uncertain",
            "warning",
            "SMTP transport failed; delivery was not recorded as successful.",
            {"outbox_id": action["id"], "error_type": type(exc).__name__},
        )
        return {"outbox_id": action["id"], "status": "uncertain", "reason": type(exc).__name__}

    evidence = _message_evidence(message)
    db.complete_action(str(action["id"]))
    db.record_evidence(
        str(action["campaign_id"]),
        "email_smtp_accepted",
        transport_evidence or evidence,
        campaign_job_id=str(action.get("campaign_job_id") or "") or None,
        metadata={"message_digest": evidence, "attachment_count": len(list(message.iter_attachments()))},
    )
    db.add_campaign_event(
        str(action["campaign_id"]),
        "email_delivery_accepted",
        "info",
        "Gmail SMTP accepted an Auditor-approved CV-attached application email.",
        {"outbox_id": action["id"], "message_digest": evidence},
    )
    return {"outbox_id": action["id"], "status": "accepted", "evidence": evidence}


def dispatch_pending(*, limit: int = 5, send_fn: Callable[[EmailMessage, str, str], str] = _smtp_send) -> dict[str, Any]:
    """Claim and dispatch a bounded batch only when delivery is explicitly configured."""
    if not _enabled():
        return {"enabled": False, "claimed": 0, "results": []}
    if not _sender() or not _password():
        return {"enabled": True, "configuration": "incomplete", "claimed": 0, "results": []}
    actions = db.claim_ready_actions(ACTION_TYPE, limit=limit)
    results = [dispatch_one(action, send_fn=send_fn) for action in actions]
    return {"enabled": True, "claimed": len(actions), "results": results}


__all__ = ["ACTION_TYPE", "dispatch_pending", "dispatch_one", "queue_audited_email_application"]

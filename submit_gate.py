#!/usr/bin/env python3
"""Single fail-closed chokepoint for employer-facing submission.

Every live sender/submitter must call ``guard`` or use ``requires_approval``
before any employer-facing side effect. Successful submissions must then call
``mark_submitted`` with concrete evidence.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from draft_review import approval_integrity_valid, is_submittable

AUDIT_LOG = os.environ.get("AUTOAPPLY_SUBMIT_AUDIT", "submit_audit.jsonl")
_audit_lock = threading.Lock()


class SubmissionRefused(RuntimeError):
    def __init__(self, reason: str, rec: dict[str, Any]) -> None:
        self.reason = reason
        self.posting = f"{rec.get('source', '?')}|{rec.get('posting_id', '?')}"
        super().__init__(f"submission refused [{self.posting}]: {reason}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _audit(event: str, rec: dict[str, Any], **extra: Any) -> None:
    draft = rec.get("_draft") or {}
    entry = {
        "at": _now(),
        "event": event,
        "source": rec.get("source"),
        "posting_id": rec.get("posting_id"),
        "company": rec.get("company"),
        "title": rec.get("title"),
        "state": rec.get("_state"),
        "approved_by": draft.get("approved_by"),
        "approved_at": draft.get("approved_at"),
        "approval_digest": draft.get("approval_digest"),
        **extra,
    }
    try:
        with _audit_lock, open(AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def refusal_reason(rec: dict[str, Any]) -> str | None:
    if not isinstance(rec, dict):
        return "no job record passed to submitter"
    state = rec.get("_state")
    draft = rec.get("_draft") or {}
    if state == "submitted_verified" or rec.get("_submission"):
        return "record is already submitted_verified"
    if state != "audit_approved":
        return f"state is {state!r}, expected 'audit_approved'"
    if not draft.get("approved_by"):
        return "no human approver recorded"
    if not draft.get("approved_at"):
        return "no approval timestamp recorded"
    if draft.get("flagged_claims"):
        return f"{len(draft['flagged_claims'])} ungrounded claim(s) still flagged"
    if not str(draft.get("cover_letter") or "").strip():
        return "approved draft has an empty cover letter"
    if not draft.get("approval_digest"):
        return "approval integrity digest missing"
    if not approval_integrity_valid(rec):
        return "approved content changed after human approval"
    return None


def guard(rec: dict[str, Any]) -> None:
    reason = refusal_reason(rec)
    if reason is not None:
        _audit("refused", rec if isinstance(rec, dict) else {}, reason=reason)
        raise SubmissionRefused(reason, rec if isinstance(rec, dict) else {})
    if not is_submittable(rec):
        _audit("refused", rec, reason="is_submittable() returned False")
        raise SubmissionRefused("is_submittable() returned False", rec)


def requires_approval(fn: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        rec = kwargs.get("rec") if "rec" in kwargs else (args[0] if args else None)
        if not isinstance(rec, dict):
            raise SubmissionRefused("no canonical job record passed to submitter", {})
        guard(rec)
        _audit("submit_attempt", rec, adapter=fn.__module__ or fn.__name__)
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            _audit("submit_failed", rec, adapter=fn.__name__, error=repr(exc)[:300])
            raise
        _audit("submit_succeeded", rec, adapter=fn.__name__)
        return result
    return wrapper


def validate_submission_evidence(evidence: dict[str, Any], *, channel: str | None = None) -> None:
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("submitted_verified requires submission evidence")
    meaningful = {k: v for k, v in evidence.items() if v not in (None, "", False, [], {})}
    if not meaningful or set(meaningful) <= {"ok", "submitted"}:
        raise ValueError("submission evidence must contain concrete provider or confirmation proof")

    channel = (channel or "").strip().lower()
    if channel == "email":
        keys = {"message_id", "smtp_message_id", "provider_message_id", "transport_evidence"}
        if not any(str(meaningful.get(key) or "").strip() for key in keys):
            raise ValueError("email submission requires a provider/SMTP message identifier")
    elif channel in {"portal", "greenhouse", "lever", "ashby", "browser", "local"}:
        keys = {
            "confirmation_id", "confirmation_url", "status", "success_marker",
            "confirmation_digest", "screenshot_path",
        }
        if not any(meaningful.get(key) not in (None, "", False) for key in keys):
            raise ValueError("portal submission requires confirmation evidence")


def mark_submitted(
    rec: dict[str, Any], *, evidence: dict[str, Any], channel: str | None = None
) -> dict[str, Any]:
    guard(rec)
    validate_submission_evidence(evidence, channel=channel)
    out = dict(rec)
    out["_state"] = "submitted_verified"
    out["_submission"] = {"at": _now(), "channel": channel or "unknown", "evidence": evidence}
    _audit("submitted_verified", out, evidence_keys=sorted(evidence), channel=channel or "unknown")
    return out


__all__ = [
    "SubmissionRefused", "guard", "mark_submitted", "refusal_reason",
    "requires_approval", "validate_submission_evidence",
]

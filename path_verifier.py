#!/usr/bin/env python3
"""Path Verifier — the missing layer between sourcing and the Auditor.

Classifies every normalized job into exactly one truthful path state. The
verifier performs READ-ONLY checks only; it never opens a session, submits a
form, or spends browser/captcha capacity.

States (per governance, this revision):
  portal_upload_unverified  a resume <input type=file> was observed on the form,
                            but the source has NOT yet proven real CV file upload
                            via a source-specific E2E. Held — not eligible.
  portal_complex            unsupported conditional steps (extra questions, consent,
                            EEO, salary expectation, cover-letter required) OR
                            insufficient evidence to classify — fails closed.
  login_or_captcha          login / account-creation / CAPTCHA / anti-bot control
                            present -> stop, do not bypass.
  expired_or_duplicate      closed listing or already attempted in repost window.

A job becomes eligible for a source-specific submit adapter only after it is
classified ``portal_upload_unverified`` AND an adapter has proven a real CV file
upload for that source (mark_source_upload_verified).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Evidence markers used during read-only classification of job/board text.
_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_LOGIN_MARKERS = ("sign in", "log in", "login required", "create an account to apply",
                  "register to apply", "captcha", "recaptcha", "hcaptcha",
                  "prove you are human", "verify you are human")
_COMPLEX_MARKERS = ("additional questions", "consent", "eeo", "equal opportunity",
                    "custom questions", "upload portfolio", "work authorization",
                    "salary expectation", "cover letter required")
_CLOSED_MARKERS = ("position closed", "no longer accepting", "applications are closed",
                   "this role has been filled", "expired")

# Optional injected resume-input evidence from a source adapter's read-only probe.
# Keyed by source; value True means a resume <input type=file> was observed.
_VERIFIED_UPLOAD_SOURCES: set[str] = set()


def mark_source_upload_verified(source: str) -> None:
    """Record that a source adapter has proven real CV file upload (post-E2E)."""
    _VERIFIED_UPLOAD_SOURCES.add(source)


def clear_verified_uploads() -> None:
    _VERIFIED_UPLOAD_SOURCES.clear()


@dataclass
class PathDecision:
    state: str
    source: str
    company: str
    title: str
    evidence: str
    eligible_for_submit: bool = False
    blocker: str = ""
    notes: list[str] = field(default_factory=list)


def verify(
    rec: dict[str, Any],
    *,
    email_address: str | None = None,
    resume_input_seen: bool = False,
    required_fields: list[str] | None = None,
    raw_text: str = "",
) -> PathDecision:
    """Classify one normalized job. Pure + read-only.

    ``email_address``: a verified employer/recruiter address (else None).
    ``resume_input_seen``: from a read-only probe of the hosted form HTML.
    ``required_fields``: fields the adapter positively discovered.
    ``raw_text``: job/board page text used for marker detection.
    """
    source = rec.get("source", "")
    company = rec.get("company", "")
    title = rec.get("title", "")
    text = (raw_text or "").lower()
    notes: list[str] = []

    # 1. Expired / closed
    if any(m in text for m in _CLOSED_MARKERS) or (
        "closed" in text and any(w in text for w in
                                 ("position", "role", "listing", "application", "job", "requisition"))
    ):
        return PathDecision("expired_or_duplicate", source, company, title,
                            "closed-marker in listing text", blocker="listing closed",
                            notes=["Marked closed by source text."])

    # 2. Login / CAPTCHA -> stop, do not bypass.
    if any(m in text for m in _LOGIN_MARKERS):
        return PathDecision("login_or_captcha", source, company, title,
                            "anti-bot/login marker detected", blocker="login or captcha control present",
                            notes=["Detected login/CAPTCHA; per governance, record and stop."])

    # 3. Direct email lane (Tier C / recruiter contact) -> routed to audited email, not portal.
    if email_address and _EMAIL_RE.match(email_address):
        return PathDecision("portal_complex", source, company, title,
                            f"verified address {email_address}",
                            blocker="routed to separate audited email lane",
                            notes=["Email lane is handled by the email adapter, not portal submit."])

    # 4. Portal upload unverified — resume input positively observed but the
    #    source has not yet proven real CV file upload via E2E.
    if resume_input_seen and required_fields is not None:
        if source in _VERIFIED_UPLOAD_SOURCES:
            return PathDecision("portal_upload_unverified", source, company, title,
                                "resume <input type=file> confirmed; source upload proven",
                                eligible_for_submit=True,
                                notes=[f"Required fields: {', '.join(required_fields) or 'unknown'}."])
        return PathDecision("portal_upload_unverified", source, company, title,
                            "resume <input type=file> confirmed; source upload NOT yet proven",
                            blocker="source CV upload not yet proven via E2E",
                            notes=["Held pending source-specific upload proof."])

    # 5. Portal complex / insufficient evidence -> not eligible (fails closed).
    return PathDecision(
        "portal_complex", source, company, title,
        "unsupported conditional steps or insufficient evidence",
        blocker="complex form markers or missing resume-upload evidence",
        notes=["Fails closed; cannot be routed to a submit adapter yet."],
    )


def classify_batch(records: list[dict[str, Any]], **kwargs: Any) -> list[PathDecision]:
    return [verify(r, **kwargs) for r in records]

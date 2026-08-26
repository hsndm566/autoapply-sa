"""Optional, fail-safe email-body personalization through the API gateway.

The sender remains authoritative for consent, approval, queueing, and delivery. This
module only turns a successful factual `/tailor` summary into an optional draft
before the existing auditor approves the immutable email package. Any unavailable,
invalid, or unexpected gateway result returns ``None`` so callers retain their
existing deterministic draft.
"""
from __future__ import annotations

import html
import os
from collections.abc import Mapping
from typing import Any

import httpx

TAILOR_ENDPOINT = "https://saudi-whatsapp-chatbot-production.up.railway.app/tailor"
FEATURE_FLAG = "ENABLE_EMAIL_PERSONALIZATION"
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_EMAIL_BODY_CHARACTERS = 2_500
MIN_SUMMARY_CHARACTERS = 40


def personalization_enabled() -> bool:
    """Return true only for the exact opt-in value required by scheduled delivery."""

    return os.environ.get(FEATURE_FLAG) == "true"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _job_context(company: str, role: str, city: str, job_description_text: str) -> str:
    """Supply a factual minimum context when a detailed job description is absent."""

    provided = _text(job_description_text)
    if provided:
        return provided
    location = city or "not specified"
    return f"Role: {role}\nCompany: {company}\nLocation: {location}"


def _build_email_body(candidate_name: str, company: str, role: str, summary: str) -> str | None:
    """Wrap an API-provided factual summary in the sender's required email structure."""

    body = (
        f"Dear {html.escape(company)} Hiring Team,\n\n"
        f"My name is {html.escape(candidate_name)}, and I am writing to apply for the "
        f"{html.escape(role)} role at {html.escape(company)}.\n\n"
        f"{summary}\n\n"
        "My CV is attached for your review.\n\n"
        "Kind regards,\n"
        f"{html.escape(candidate_name)}\n\n"
        "If you'd prefer not to receive future applications from this platform, reply STOP."
    )
    if len(body) < 80 or len(body) > MAX_EMAIL_BODY_CHARACTERS:
        return None
    return body


async def personalize_email_body(
    *,
    candidate_profile: Mapping[str, Any],
    company: str,
    role: str,
    city: str = "",
    job_description_text: str = "",
    client: httpx.AsyncClient | Any | None = None,
) -> str | None:
    """Return an optional factual email body, or ``None`` for the generic fallback.

    The gateway returns a resume-tailoring summary rather than a mail-ready draft.
    The sender wraps that summary in its existing company/role-specific, opt-out
    structure and rejects malformed responses before the normal audit boundary.
    """

    candidate_name = _text(candidate_profile.get("full_name"))
    company, role = _text(company), _text(role)
    if not candidate_name or not company or not role:
        return None
    payload = {
        "structured_profile_json": dict(candidate_profile),
        "job_description_text": _job_context(company, role, _text(city), job_description_text),
    }
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as request_client:
                response = await request_client.post(TAILOR_ENDPOINT, json=payload)
        else:
            response = await client.post(TAILOR_ENDPOINT, json=payload)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, Mapping) or result.get("status") != "ok":
            return None
        summary = _text(result.get("summary"))
        return _build_email_body(candidate_name, company, role, summary) if len(summary) >= MIN_SUMMARY_CHARACTERS else None
    except Exception:
        # Personalization must never delay, fail, or change the outcome of delivery.
        return None


__all__ = ["FEATURE_FLAG", "TAILOR_ENDPOINT", "personalization_enabled", "personalize_email_body"]

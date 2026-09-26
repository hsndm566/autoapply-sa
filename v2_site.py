"""Evidence-backed V2 customer application path.

A signed-in customer explicitly selects one verified job and presses Send. The server
re-loads the job, profile, and private CV from Supabase. Email is exposed only when the
existing verified-contact store has an exact employer match, and delivery goes through
the existing Auditor + durable email dispatcher before the V2 record is reconciled.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
import v2_verified_email

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
BREVO_ACCOUNT_ENDPOINT = "https://api.brevo.com/v3/account"
CV_BUCKET = "candidate-cvs"
MAX_CV_BYTES = 10 * 1024 * 1024


class V2Error(RuntimeError):
    def __init__(self, reason: str, status: int = 502) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.environ.get("SUPABASE_ANON_KEY", "").strip()
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
    )
    if not url or not key:
        raise V2Error("supabase-auth-not-configured", 503)
    return url, key


def _headers(token: str, *, return_representation: bool = False) -> dict[str, str]:
    _url, key = _supabase_config()
    result = {
        "Authorization": f"Bearer {token}",
        "apikey": key,
        "accept": "application/json",
        "content-type": "application/json",
    }
    if return_representation:
        result["Prefer"] = "return=representation"
    return result


def _request_json(
    method: str,
    table: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    return_representation: bool = False,
) -> list[dict[str, Any]]:
    url, _key = _supabase_config()
    try:
        response = requests.request(
            method,
            f"{url}/rest/v1/{table}",
            headers=_headers(token, return_representation=return_representation),
            params=params,
            json=body,
            timeout=12,
        )
    except requests.RequestException as exc:
        raise V2Error("supabase-data-unavailable", 502) from exc

    if response.status_code >= 400:
        if response.status_code == 409:
            raise V2Error("duplicate-application", 409)
        raise V2Error("supabase-data-rejected", 502)

    if response.status_code == 204 or not response.content:
        return []
    try:
        payload = response.json()
    except ValueError as exc:
        raise V2Error("supabase-invalid-response", 502) from exc
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise V2Error("supabase-invalid-response", 502)


def readiness() -> dict[str, Any]:
    try:
        _supabase_config()
    except V2Error as exc:
        return {"ok": False, "error": exc.reason, "status": exc.status}

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "brevo-not-configured", "status": 503}
    try:
        response = requests.get(
            BREVO_ACCOUNT_ENDPOINT,
            headers={"api-key": api_key, "accept": "application/json"},
            timeout=8,
        )
    except requests.RequestException:
        return {"ok": False, "error": "brevo-readiness-failed", "status": 502}
    if not response.ok:
        return {"ok": False, "error": "brevo-readiness-failed", "status": response.status_code}
    return {"ok": True, "status": 200}


def _words(value: str) -> list[str]:
    return [part for part in re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", value.casefold()).split() if len(part) >= 3]


def _matches(text: str, token: str) -> bool:
    if token in text:
        return True
    stem = token[: max(5, len(token) - 3)] if len(token) >= 7 else token
    return len(stem) >= 5 and stem in text


def _score_job(job: dict[str, Any], role: str, city: str) -> int:
    searchable = f"{job.get('title', '')} {job.get('description', '')}".casefold()
    location = str(job.get("location") or "").casefold()
    role_matches = sum(1 for token in _words(role) if _matches(searchable, token))
    city_match = 5 if city.strip() and city.strip().casefold() in location else 0
    saudi = 1 if re.search(r"saudi|ksa|riyadh|jeddah|dammam|khobar", location) else 0
    return role_matches * 4 + city_match + saudi


def recommended_jobs(token: str, *, role: str, city: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = _request_json(
        "GET",
        "v2_live_jobs",
        token,
        params={
            "select": "id,canonicalUrl,company,title,location,description,lastSeenAt,verifiedUntil,verification",
            "order": "lastSeenAt.desc",
            "limit": "100",
        },
    )
    ranked = sorted(
        ((row, _score_job(row, role, city)) for row in rows),
        key=lambda item: (item[1], str(item[0].get("lastSeenAt") or "")),
        reverse=True,
    )
    output: list[dict[str, Any]] = []
    for job, score in ranked:
        if score <= 0:
            continue
        title = str(job.get("title") or "").strip()
        company = str(job.get("company") or "").strip()
        source_url = str(job.get("canonicalUrl") or "").strip()
        if not title or not company or not source_url.startswith(("http://", "https://")):
            continue
        location = str(job.get("location") or "Saudi Arabia").strip() or "Saudi Arabia"
        reasons: list[str] = []
        if any(_matches(title.casefold(), token_word) for token_word in _words(role)):
            reasons.append(f"title aligns with {role}")
        if city.strip() and city.strip().casefold() in location.casefold():
            reasons.append(f"location matches {city}")
        if not reasons:
            reasons.append("verified Saudi opportunity from a public ATS")
        capability = v2_verified_email.email_capability(company)
        output.append(
            {
                "id": str(job.get("id") or ""),
                "companyName": company,
                "roleTitle": title,
                "city": location,
                "source": str(job.get("verification") or "verified_public_ats"),
                "url": source_url,
                "summary": str(job.get("description") or "Verified public ATS posting.")[:500],
                "matchReason": " · ".join(reasons),
                "freshness": str(job.get("lastSeenAt") or ""),
                **capability,
            }
        )
        if len(output) >= limit:
            break
    return output


def _one(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[0] if rows else None


def _profile(token: str, user_id: str) -> dict[str, Any] | None:
    return _one(
        _request_json(
            "GET",
            "v2_profiles",
            token,
            params={
                "select": "fullName,targetRole,targetIndustry,experienceLevel,resumeFileName,resumeSummary,resumeStoragePath,resumeMimeType,resumeSizeBytes",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )
    )


def _job(token: str, job_id: str) -> dict[str, Any] | None:
    try:
        uuid.UUID(job_id)
    except (ValueError, AttributeError) as exc:
        raise V2Error("verified-job-not-found", 404) from exc
    return _one(
        _request_json(
            "GET",
            "v2_live_jobs",
            token,
            params={
                "select": "id,canonicalUrl,company,title,location,description,lastSeenAt,verifiedUntil,verification",
                "id": f"eq.{job_id}",
                "limit": "1",
            },
        )
    )


def _download_cv(token: str, user_id: str, profile: dict[str, Any]) -> tuple[bytes, str]:
    path = str(profile.get("resumeStoragePath") or "").strip()
    name = str(profile.get("resumeFileName") or "").strip()
    if not path or not name:
        raise V2Error("cv-required", 409)
    if not path.startswith(f"{user_id}/"):
        raise V2Error("cv-ownership-mismatch", 409)

    url, _key = _supabase_config()
    object_url = f"{url}/storage/v1/object/authenticated/{CV_BUCKET}/{quote(path, safe='/')}"
    try:
        response = requests.get(object_url, headers=_headers(token), timeout=15)
    except requests.RequestException as exc:
        raise V2Error("cv-download-failed", 502) from exc
    if response.status_code >= 400:
        raise V2Error("cv-download-failed", 502)
    payload = response.content
    if not payload or len(payload) > MAX_CV_BYTES:
        raise V2Error("cv-size-invalid", 409)
    return payload, re.sub(r'[\\/\r\n"]+', "_", name)[:180] or "CV.pdf"


def _grounded_message(profile: dict[str, Any], job: dict[str, Any]) -> str:
    summary = ", ".join(
        value.strip()
        for value in str(profile.get("resumeSummary") or "").split(",")
        if value.strip()
    )
    summary = ", ".join(summary.split(", ")[:8])
    lines = [
        f"Hello {job.get('company', '')} team,",
        "",
        f"I am applying for the {job.get('title', '')} role"
        + (f" in {job.get('location')}" if job.get("location") else "")
        + ".",
        (
            f"The CV keywords identified during my profile setup include: {summary}."
            if summary
            else "Please find my CV attached for your review."
        ),
        "",
        "I would appreciate the opportunity to discuss the role.",
    ]
    return "\n".join(lines)


def _existing_application(token: str, user_id: str, source_url: str) -> dict[str, Any] | None:
    return _one(
        _request_json(
            "GET",
            "v2_applications",
            token,
            params={
                "select": "*",
                "user_id": f"eq.{user_id}",
                "sourceUrl": f"eq.{source_url}",
                "limit": "1",
            },
        )
    )


def _reserve_application(
    token: str,
    user_id: str,
    job: dict[str, Any],
    to_email: str,
    cv_path: str,
) -> dict[str, Any]:
    source_url = str(job.get("canonicalUrl") or "")
    existing = _existing_application(token, user_id, source_url)
    if existing and (existing.get("status") == "applied" or existing.get("providerMessageId")):
        raise V2Error("duplicate-application", 409)

    row = {
        "user_id": user_id,
        "companyName": str(job.get("company") or ""),
        "roleTitle": str(job.get("title") or ""),
        "city": str(job.get("location") or "Saudi Arabia"),
        "status": "queued",
        "updatedAt": _now(),
        "recipientEmail": to_email,
        "deliveryStatus": "unknown",
        "responseStatus": "none",
        "responseNote": None,
        "source": str(job.get("verification") or "verified_public_ats"),
        "sourceUrl": source_url,
        "cvStoragePath": cv_path,
        "jobId": str(job.get("id") or ""),
        "providerMessageId": None,
    }

    if existing:
        updated = _request_json(
            "PATCH",
            "v2_applications",
            token,
            params={"id": f"eq.{existing['id']}", "user_id": f"eq.{user_id}"},
            body=row,
            return_representation=True,
        )
        if not updated:
            raise V2Error("application-reservation-failed", 502)
        return updated[0]

    created = _request_json(
        "POST",
        "v2_applications",
        token,
        body=row,
        return_representation=True,
    )
    if not created:
        raise V2Error("application-reservation-failed", 502)
    return created[0]


def _patch_application(token: str, user_id: str, application_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    rows = _request_json(
        "PATCH",
        "v2_applications",
        token,
        params={"id": f"eq.{application_id}", "user_id": f"eq.{user_id}"},
        body={**values, "updatedAt": _now()},
        return_representation=True,
    )
    return _one(rows)


def send_application(
    token: str,
    user: dict[str, Any],
    *,
    job_id: str,
) -> dict[str, Any]:
    user_id = str(user.get("id") or "").strip()
    candidate_email = str(user.get("email") or "").strip()
    if not user_id or not candidate_email:
        raise V2Error("candidate-email-required", 409)

    profile = _profile(token, user_id)
    if not profile or not str(profile.get("fullName") or "").strip():
        raise V2Error("profile-required", 409)
    if not all(str(profile.get(field) or "").strip() for field in ("targetRole", "targetIndustry", "experienceLevel")):
        raise V2Error("preferences-required", 409)

    job = _job(token, job_id)
    if not job:
        raise V2Error("verified-job-not-found", 404)

    contact = v2_verified_email.verified_contact_for_company(str(job.get("company") or ""))
    if not contact:
        raise V2Error("verified-recipient-required", 409)

    cv_bytes, cv_name = _download_cv(token, user_id, profile)
    cv_path = str(profile.get("resumeStoragePath") or "")
    application = _reserve_application(token, user_id, job, str(contact["email"]), cv_path)
    application_id = str(application.get("id") or "")
    source_url = str(job.get("canonicalUrl") or "")

    def accounting_check() -> bool:
        current = _existing_application(token, user_id, source_url)
        return bool(
            current
            and str(current.get("id") or "") == application_id
            and str(current.get("status") or "") == "queued"
            and str(current.get("recipientEmail") or "").casefold() == str(contact["email"]).casefold()
        )

    try:
        result = v2_verified_email.dispatch_v2_application(
            user_id=user_id,
            candidate_email=candidate_email,
            candidate_name=str(profile.get("fullName") or "").strip(),
            job=job,
            contact=contact,
            cv_bytes=cv_bytes,
            cv_name=cv_name,
            draft=_grounded_message(profile, job),
            v2_application_id=application_id,
            accounting_check=accounting_check,
        )
    except v2_verified_email.V2VerifiedEmailError as exc:
        if application_id:
            try:
                _patch_application(
                    token,
                    user_id,
                    application_id,
                    {"status": "queued", "deliveryStatus": "blocked", "responseNote": exc.reason},
                )
            except V2Error:
                pass
        raise V2Error(exc.reason, exc.status) from exc

    message_id = str(result.get("transport_evidence") or "").strip()
    if not message_id:
        raise V2Error("provider-evidence-missing", 502)

    sent_at = _now()
    updated = _patch_application(
        token,
        user_id,
        application_id,
        {
            "status": "applied",
            "appliedAt": sent_at,
            "deliveryStatus": "sent",
            "providerMessageId": message_id,
            "responseNote": None,
        },
    )
    if not updated:
        raise V2Error("application-reconciliation-failed", 502)
    return {"ok": True, "messageId": message_id, "application": updated}


__all__ = ["V2Error", "readiness", "recommended_jobs", "send_application"]

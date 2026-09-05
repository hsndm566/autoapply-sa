#!/usr/bin/env python3
"""Grounded drafting and explicit human approval state machine.

This module never submits anything. Drafting can only reach ``drafted`` or
``needs_review``. Only ``approve_draft`` can create ``audit_approved``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from job_schema import PATH_STATES, STATES  # noqa: F401

DRAFTABLE_PATHS = ("direct_email", "portal_upload_verified")
MAX_LETTER_WORDS = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9\u0600-\u06ff]+", _norm(text)) if len(t) > 2}


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def check_grounding(
    claims: Iterable[str], profile_text: str, *, threshold: float = 0.6
) -> tuple[list[str], list[str]]:
    profile_tokens = _tokens(profile_text)
    grounded: list[str] = []
    ungrounded: list[str] = []
    for claim in claims:
        claim_tokens = _tokens(claim)
        if not claim_tokens:
            continue
        overlap = len(claim_tokens & profile_tokens) / len(claim_tokens)
        (grounded if overlap >= threshold else ungrounded).append(claim)
    return grounded, ungrounded


def build_prompt(rec: dict[str, Any], profile: dict[str, Any], lang: str = "en") -> str:
    lang_line = (
        "Write every field in Modern Standard Arabic."
        if lang == "ar"
        else "Write every field in English."
    )
    return f"""You prepare job applications for candidates in Saudi Arabia.

Use ONLY facts that appear in the candidate profile below. Do not invent
employers, job titles, dates, degrees, certifications, tools or metrics. If the
opening asks for something the profile does not evidence, put it in \"gaps\".

CANDIDATE PROFILE
{profile.get('full_text', '')}

OPENING
{rec.get('title', '')} at {rec.get('company', '')}
Location: {rec.get('location', '')}
Type: {rec.get('employment_type', '')}
Apply via: {rec.get('application_mode', '')}
Description:
{rec.get('description', '')[:4000]}

{lang_line}
The cover letter must be under {MAX_LETTER_WORDS} words.

Respond with ONLY a JSON object, no markdown fences:
{{
  \"match_score\": <integer 0-100>,
  \"evidence\": [<2-5 factual strings grounded in the profile>],
  \"gaps\": [<1-3 strings naming requirements not evidenced by the profile>],
  \"subject\": \"<subject line>\",
  \"cover_letter\": \"<plain text>\",
  \"cv_highlights\": [<2-4 existing profile facts>]
}}"""


def _hold(rec: dict[str, Any], reason: str, detail: Any = None) -> dict[str, Any]:
    out = dict(rec)
    out["_state"] = "needs_review"
    out["_review"] = {"reason": reason, "detail": detail, "at": _now()}
    return out


def build_draft(
    rec: dict[str, Any],
    profile: dict[str, Any],
    complete: Callable[[str], str],
    *,
    lang: str = "en",
    grounding_threshold: float = 0.6,
) -> dict[str, Any]:
    if not (profile.get("full_text") or "").strip():
        return _hold(rec, "empty_profile")
    if rec.get("_path") not in DRAFTABLE_PATHS:
        return _hold(rec, "path_not_draftable", rec.get("_path"))

    missing = [f for f in rec.get("required_fields", []) if not profile.get(f)]
    if missing:
        return _hold(rec, "missing_required_field", missing)

    raw = complete(build_prompt(rec, profile, lang))
    try:
        payload = json.loads(re.sub(r"```(?:json)?", "", raw or "").strip())
    except (json.JSONDecodeError, TypeError):
        return _hold(rec, "model_malformed_output", (raw or "")[:400])
    if not isinstance(payload, dict):
        return _hold(rec, "model_malformed_output", "model output is not an object")

    evidence = payload.get("evidence") or []
    highlights = payload.get("cv_highlights") or []
    if not isinstance(evidence, list) or not isinstance(highlights, list):
        return _hold(rec, "model_malformed_output", "evidence/highlights must be arrays")

    profile_text = str(profile.get("full_text") or "")
    grounded_ev, ungrounded_ev = check_grounding(evidence, profile_text, threshold=grounding_threshold)
    grounded_hl, ungrounded_hl = check_grounding(highlights, profile_text, threshold=grounding_threshold)
    letter = str(payload.get("cover_letter") or "")

    out = dict(rec)
    out["_state"] = "drafted"
    out["_draft"] = {
        "lang": lang,
        "match_score": payload.get("match_score"),
        "subject": str(payload.get("subject") or ""),
        "cover_letter": letter,
        "cover_letter_words": _word_count(letter),
        "evidence": grounded_ev,
        "gaps": payload.get("gaps") or [],
        "cv_highlights": grounded_hl,
        "flagged_claims": ungrounded_ev + ungrounded_hl,
        "drafted_at": _now(),
        "approved_by": None,
        "approved_at": None,
        "approval_digest": None,
    }

    if ungrounded_ev or ungrounded_hl:
        held = _hold(out, "ungrounded_claim", ungrounded_ev + ungrounded_hl)
        held["_draft"] = out["_draft"]
        return held
    if not letter.strip() or _word_count(letter) > MAX_LETTER_WORDS:
        held = _hold(out, "model_malformed_output", "cover letter empty or over length")
        held["_draft"] = out["_draft"]
        return held
    return out


def approval_digest(rec: dict[str, Any], draft: dict[str, Any] | None = None) -> str:
    d = dict(draft if draft is not None else (rec.get("_draft") or {}))
    material = json.dumps(
        {
            "source": str(rec.get("source") or ""),
            "posting_id": str(rec.get("posting_id") or ""),
            "cover_letter": str(d.get("cover_letter") or ""),
            "subject": str(d.get("subject") or ""),
            "approved_by": str(d.get("approved_by") or ""),
            "approved_at": str(d.get("approved_at") or ""),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def approval_integrity_valid(rec: dict[str, Any]) -> bool:
    draft = rec.get("_draft") or {}
    stored = str(draft.get("approval_digest") or "")
    return bool(stored and hmac.compare_digest(stored, approval_digest(rec, draft)))


def approve_draft(
    rec: dict[str, Any],
    *,
    approved_by: str,
    edited_letter: str | None = None,
    edited_subject: str | None = None,
) -> dict[str, Any]:
    if not (approved_by or "").strip():
        raise ValueError("approve_draft requires a named human approver")
    if rec.get("_state") != "drafted":
        raise ValueError(f"cannot approve from state {rec.get('_state')!r}; expected 'drafted'")

    draft = dict(rec.get("_draft") or {})
    if draft.get("flagged_claims"):
        raise ValueError("cannot approve while ungrounded claims remain flagged")
    if edited_letter is not None:
        draft["cover_letter"] = edited_letter
        draft["cover_letter_words"] = _word_count(edited_letter)
        draft["human_edited"] = True
    if edited_subject is not None:
        draft["subject"] = edited_subject
        draft["human_edited"] = True
    if not str(draft.get("cover_letter") or "").strip():
        raise ValueError("cannot approve an empty cover letter")

    draft["approved_by"] = approved_by.strip()
    draft["approved_at"] = _now()
    draft["approval_digest"] = approval_digest(rec, draft)

    out = dict(rec)
    out["_draft"] = draft
    out["_state"] = "audit_approved"
    return out


def reject_draft(rec: dict[str, Any], *, rejected_by: str, note: str = "") -> dict[str, Any]:
    if not (rejected_by or "").strip():
        raise ValueError("reject_draft requires a named human actor")
    out = dict(rec)
    out["_state"] = "needs_review"
    out["_review"] = {
        "reason": "human_rejected",
        "detail": note,
        "by": rejected_by.strip(),
        "at": _now(),
    }
    return out


def is_submittable(rec: dict[str, Any]) -> bool:
    draft = rec.get("_draft") or {}
    return bool(
        rec.get("_state") == "audit_approved"
        and draft.get("approved_by")
        and draft.get("approved_at")
        and not draft.get("flagged_claims")
        and str(draft.get("cover_letter") or "").strip()
        and approval_integrity_valid(rec)
    )


def pending_review(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    held = [r for r in records if r.get("_state") in ("drafted", "needs_review")]
    return sorted(
        held,
        key=lambda r: (r.get("_review") or {}).get("at")
        or (r.get("_draft") or {}).get("drafted_at")
        or "",
        reverse=True,
    )

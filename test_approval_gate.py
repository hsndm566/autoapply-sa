#!/usr/bin/env python3
from __future__ import annotations

import json

import pytest

from draft_review import (
    approval_integrity_valid,
    approve_draft,
    build_draft,
    check_grounding,
    is_submittable,
    pending_review,
    reject_draft,
)
from submit_gate import (
    SubmissionRefused,
    guard,
    mark_submitted,
    refusal_reason,
    requires_approval,
    validate_submission_evidence,
)

PROFILE = {
    "full_text": (
        "Hasan Aldamigh. Operations coordinator in Jeddah with four years at "
        "Red Sea Logistics handling inventory planning, vendor performance "
        "reporting and SAP data entry. Advanced Excel. Bilingual Arabic and "
        "English. Bachelor of Business Administration, King Abdulaziz University."
    ),
    "email": "apply@hsndm.tech",
}

JOB = {
    "source": "greenhouse",
    "employer_key": "tamweel",
    "posting_id": "4471",
    "company": "Tamweel Industrial",
    "title": "Supply Chain Analyst",
    "location": "Riyadh",
    "employment_type": "Full time",
    "job_url": "https://example.test/jobs/4471",
    "apply_url": "https://example.test/jobs/4471/apply",
    "description": "Forecasting, vendor reporting, inventory planning. SAP required.",
    "application_mode": "portal",
    "required_fields": ["email"],
    "_state": "path_verified",
    "_path": "portal_upload_verified",
    "_raw": {},
}

GOOD = {
    "match_score": 78,
    "evidence": [
        "Four years at Red Sea Logistics in inventory planning",
        "SAP data entry and advanced Excel",
    ],
    "gaps": ["No forecasting ownership stated in the profile"],
    "subject": "Application: Supply Chain Analyst",
    "cover_letter": (
        "I have four years at Red Sea Logistics in inventory planning, "
        "SAP data entry and vendor performance reporting."
    ),
    "cv_highlights": ["Vendor performance reporting", "Advanced Excel"],
}


def fake_model(payload: dict):
    return lambda _prompt: json.dumps(payload)


def clean_draft() -> dict:
    return build_draft(JOB, PROFILE, fake_model(GOOD))


def approved() -> dict:
    return approve_draft(clean_draft(), approved_by="hasan")


def test_grounding_accepts_facts_from_profile():
    grounded, ungrounded = check_grounding(["Four years at Red Sea Logistics"], PROFILE["full_text"])
    assert grounded and not ungrounded


def test_grounding_rejects_invented_employer():
    grounded, ungrounded = check_grounding(["Six years leading procurement at Saudi Aramco"], PROFILE["full_text"])
    assert ungrounded and not grounded


def test_grounding_rejects_invented_credential():
    _, ungrounded = check_grounding(["Certified Supply Chain Professional CSCP credential holder"], PROFILE["full_text"])
    assert ungrounded


def test_clean_draft_reaches_drafted_not_approved():
    rec = clean_draft()
    assert rec["_state"] == "drafted"
    assert rec["_draft"]["approved_by"] is None


def test_build_draft_does_not_mutate_input():
    before = dict(JOB)
    clean_draft()
    assert JOB == before


def test_fabricated_claim_holds_record():
    rec = build_draft(JOB, PROFILE, fake_model(dict(GOOD, evidence=["Ten years as head of logistics at Maersk"])))
    assert rec["_state"] == "needs_review"
    assert rec["_review"]["reason"] == "ungrounded_claim"


def test_malformed_model_output_holds_record():
    rec = build_draft(JOB, PROFILE, lambda _p: "not json")
    assert rec["_review"]["reason"] == "model_malformed_output"


def test_undraftable_path_is_refused():
    rec = build_draft(dict(JOB, _path="login_or_captcha"), PROFILE, fake_model(GOOD))
    assert rec["_review"]["reason"] == "path_not_draftable"


def test_missing_required_field_is_refused():
    rec = build_draft(JOB, {"full_text": PROFILE["full_text"]}, fake_model(GOOD))
    assert rec["_review"]["reason"] == "missing_required_field"


def test_empty_profile_is_refused():
    rec = build_draft(JOB, {"full_text": "   "}, fake_model(GOOD))
    assert rec["_review"]["reason"] == "empty_profile"


def test_approval_requires_named_human():
    with pytest.raises(ValueError):
        approve_draft(clean_draft(), approved_by="")


def test_cannot_approve_held_record():
    rec = build_draft(JOB, PROFILE, fake_model(dict(GOOD, evidence=["Ten years at Maersk"])))
    with pytest.raises(ValueError):
        approve_draft(rec, approved_by="hasan")


def test_approval_records_who_when_and_digest():
    rec = approved()
    assert rec["_state"] == "audit_approved"
    assert rec["_draft"]["approved_by"] == "hasan"
    assert rec["_draft"]["approved_at"]
    assert rec["_draft"]["approval_digest"]
    assert approval_integrity_valid(rec)


def test_human_edits_are_kept_and_hashed():
    rec = approve_draft(clean_draft(), approved_by="hasan", edited_letter="My own words.")
    assert rec["_draft"]["cover_letter"] == "My own words."
    assert rec["_draft"]["human_edited"] is True
    assert approval_integrity_valid(rec)


def test_rejection_returns_to_review():
    rec = reject_draft(clean_draft(), rejected_by="hasan", note="too generic")
    assert rec["_state"] == "needs_review"
    assert rec["_review"]["detail"] == "too generic"


def test_unapproved_draft_is_not_submittable():
    assert not is_submittable(clean_draft())


def test_approved_draft_is_submittable():
    assert is_submittable(approved())


def test_guard_refuses_raw_record():
    with pytest.raises(SubmissionRefused):
        guard(JOB)


def test_guard_refuses_hand_forged_state():
    with pytest.raises(SubmissionRefused):
        guard(dict(JOB, _state="audit_approved"))


def test_guard_refuses_approval_without_timestamp():
    rec = approved()
    rec["_draft"] = dict(rec["_draft"], approved_at=None)
    with pytest.raises(SubmissionRefused):
        guard(rec)


def test_guard_refuses_cover_letter_changed_after_approval():
    rec = approved()
    rec["_draft"] = dict(rec["_draft"], cover_letter="Changed after approval")
    assert not approval_integrity_valid(rec)
    with pytest.raises(SubmissionRefused):
        guard(rec)


def test_guard_refuses_subject_changed_after_approval():
    rec = approved()
    rec["_draft"] = dict(rec["_draft"], subject="Different subject")
    with pytest.raises(SubmissionRefused):
        guard(rec)


def test_decorated_adapter_refuses_unapproved_without_running_body():
    calls = []

    @requires_approval
    def submit(rec):
        calls.append(rec)
        return "sent"

    with pytest.raises(SubmissionRefused):
        submit(clean_draft())
    assert calls == []


def test_decorated_adapter_runs_when_approved():
    @requires_approval
    def submit(rec):
        return "sent"

    assert submit(approved()) == "sent"


def test_submitted_verified_requires_evidence():
    with pytest.raises(ValueError):
        mark_submitted(approved(), evidence={})


def test_generic_boolean_is_not_evidence():
    with pytest.raises(ValueError):
        validate_submission_evidence({"ok": True})


def test_submitted_verified_with_portal_evidence():
    out = mark_submitted(approved(), evidence={"confirmation_id": "GH-9912", "status": 201}, channel="greenhouse")
    assert out["_state"] == "submitted_verified"


def test_email_evidence_requires_message_identifier():
    with pytest.raises(ValueError):
        validate_submission_evidence({"status": 202}, channel="email")


def test_email_evidence_accepts_message_identifier():
    validate_submission_evidence({"provider_message_id": "abc-123"}, channel="email")


def test_duplicate_submission_is_refused():
    out = mark_submitted(approved(), evidence={"confirmation_id": "GH-9912"}, channel="greenhouse")
    with pytest.raises(SubmissionRefused):
        guard(out)


def test_queue_surfaces_only_waiting_records():
    rec = clean_draft()
    assert refusal_reason(rec) is not None
    assert pending_review([rec, dict(JOB, _state="submitted_verified")]) == [rec]

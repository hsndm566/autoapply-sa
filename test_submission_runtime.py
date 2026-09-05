#!/usr/bin/env python3
from __future__ import annotations

import json

import pytest

import submission_runtime
from draft_review import approve_draft, build_draft
from submit_gate import SubmissionRefused, mark_submitted

PROFILE = {
    "full_text": "Candidate has four years of inventory planning and advanced Excel experience.",
    "email": "candidate@example.test",
}

JOB = {
    "source": "greenhouse",
    "posting_id": "jobhash-1",
    "company": "Example Co",
    "title": "Operations Analyst",
    "location": "Riyadh",
    "job_url": "https://example.test/jobs/1",
    "apply_url": "https://example.test/jobs/1/apply",
    "description": "Inventory planning and Excel",
    "application_mode": "portal",
    "required_fields": ["email"],
    "_state": "path_verified",
    "_path": "portal_upload_verified",
    "_raw": {"campaign_job_id": "cj-1"},
    "_campaign_id": "campaign-1",
}

MODEL = {
    "match_score": 80,
    "evidence": ["four years of inventory planning", "advanced Excel experience"],
    "gaps": [],
    "subject": "Operations Analyst application",
    "cover_letter": "I have four years of inventory planning and advanced Excel experience.",
    "cv_highlights": ["advanced Excel experience"],
}


def _complete(_prompt: str) -> str:
    return json.dumps(MODEL)


def drafted() -> dict:
    return build_draft(JOB, PROFILE, _complete)


def approved() -> dict:
    rec = approve_draft(drafted(), approved_by="campaign-owner")
    rec["_campaign_id"] = "campaign-1"
    return rec


def approved_email() -> dict:
    rec = {
        "source": "email",
        "posting_id": "email-app-1",
        "company": "Example Co",
        "title": "Operations Analyst",
        "job_url": "https://example.test/jobs/email-1",
        "_campaign_id": "campaign-1",
        "_path": "direct_email",
        "_state": "drafted",
        "_draft": {
            "cover_letter": "I have four years of inventory planning and advanced Excel experience.",
            "subject": "Operations Analyst application",
            "flagged_claims": [],
            "approved_by": None,
            "approved_at": None,
        },
        "_raw": {
            "contact_id": "contact-1",
            "application_id": "email-app-1",
            "recipient": "recruiter@example.test",
        },
    }
    return approve_draft(rec, approved_by="campaign-owner")


class FakeStore:
    def __init__(self, rec: dict):
        self.rec = rec
        self.saved: list[dict] = []

    def get_record(self, source: str, posting_id: str):
        if source == self.rec.get("source") and posting_id == self.rec.get("posting_id"):
            return self.rec
        return None

    def save_record(self, rec: dict):
        self.rec = rec
        self.saved.append(rec)


def install(monkeypatch, rec: dict, adapter):
    store = FakeStore(rec)
    monkeypatch.setattr(submission_runtime, "CampaignReviewStore", lambda _campaign_id: store)
    monkeypatch.setattr(
        submission_runtime.db,
        "get_campaign",
        lambda _campaign_id: {
            "candidate_name": "Test Candidate",
            "candidate_email": "candidate@example.test",
            "cv_path": "/private/candidate.pdf",
        },
    )
    monkeypatch.setattr(submission_runtime.db, "record_evidence", lambda *a, **k: None)
    monkeypatch.setattr(submission_runtime.db, "add_campaign_event", lambda *a, **k: None)
    monkeypatch.setattr(submission_runtime, "_adapter", lambda _source: adapter)
    return store


def test_unapproved_record_never_reaches_adapter(monkeypatch):
    calls = []
    rec = drafted()
    rec["_campaign_id"] = "campaign-1"
    install(monkeypatch, rec, lambda *_a, **_k: calls.append(True))
    with pytest.raises(SubmissionRefused):
        submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert calls == []


def test_verified_success_is_persisted(monkeypatch):
    rec = approved()

    def adapter(approved_rec, _candidate):
        out = mark_submitted(
            approved_rec,
            evidence={"confirmation_url": "https://example.test/confirmation", "success_marker": "thank you"},
            channel="greenhouse",
        )
        return {
            "ok": True,
            "submitted": True,
            "record": out,
            "evidence": out["_submission"]["evidence"],
        }

    store = install(monkeypatch, rec, adapter)
    result = submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert result["status"] == "submitted_verified"
    assert store.rec["_state"] == "submitted_verified"
    assert store.saved[-1]["_submission"]["evidence"]["confirmation_url"]


def test_duplicate_verified_record_is_refused_before_adapter(monkeypatch):
    rec = mark_submitted(
        approved(),
        evidence={"confirmation_id": "already-sent"},
        channel="greenhouse",
    )
    calls = []
    install(monkeypatch, rec, lambda *_a, **_k: calls.append(True))
    with pytest.raises(SubmissionRefused):
        submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert calls == []


def test_captcha_result_is_held_and_not_marked_submitted(monkeypatch):
    rec = approved()
    store = install(
        monkeypatch,
        rec,
        lambda *_a, **_k: {
            "ok": False,
            "submitted": False,
            "status": "manual_handoff",
            "reason": "login_or_captcha",
        },
    )
    result = submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert result["status"] == "needs_review"
    assert result["hold_reason"] == "manual_challenge"
    assert store.rec["_state"] == "needs_review"
    assert "_submission" not in store.rec


def test_uncertain_post_click_result_blocks_automatic_retry(monkeypatch):
    store = install(
        monkeypatch,
        approved(),
        lambda *_a, **_k: {
            "ok": False,
            "submitted": False,
            "status": "uncertain",
            "reason": "no_confirmation_observed",
        },
    )
    result = submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert result["hold_reason"] == "submission_uncertain"
    assert store.rec["_state"] == "needs_review"


def test_cross_campaign_record_is_refused_before_adapter(monkeypatch):
    rec = approved()
    rec["_campaign_id"] = "other-campaign"
    calls = []
    install(monkeypatch, rec, lambda *_a, **_k: calls.append(True))
    with pytest.raises(PermissionError):
        submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert calls == []


def test_missing_candidate_artifact_fails_before_adapter(monkeypatch):
    rec = approved()
    store = FakeStore(rec)
    calls = []
    monkeypatch.setattr(submission_runtime, "CampaignReviewStore", lambda _campaign_id: store)
    monkeypatch.setattr(
        submission_runtime.db,
        "get_campaign",
        lambda _campaign_id: {"candidate_name": "Test Candidate", "candidate_email": "candidate@example.test", "cv_path": ""},
    )
    monkeypatch.setattr(submission_runtime, "_adapter", lambda _source: lambda *_a, **_k: calls.append(True))
    with pytest.raises(ValueError):
        submission_runtime.submit_approved("campaign-1", "greenhouse", "jobhash-1")
    assert calls == []


def test_approved_email_is_queued_with_exact_human_record(monkeypatch):
    rec = approved_email()
    store = FakeStore(rec)
    calls: list[dict] = []
    monkeypatch.setattr(submission_runtime, "CampaignReviewStore", lambda _campaign_id: store)

    def queue_email(campaign_id, contact_id, **kwargs):
        calls.append({"campaign_id": campaign_id, "contact_id": contact_id, **kwargs})
        return {"queued": True, "outbox_id": "outbox-1", "audit_status": "approved"}

    monkeypatch.setattr(submission_runtime.campaign_email, "prepare_audited_campaign_email", queue_email)
    result = submission_runtime.submit_approved("campaign-1", "email", "email-app-1")
    assert result["status"] == "queued_for_delivery"
    assert result["outbox_id"] == "outbox-1"
    assert calls[0]["human_approval_record"]["_draft"]["approval_digest"]
    assert store.rec["_submission_intent"]["outbox_id"] == "outbox-1"


def test_email_submit_cannot_be_queued_twice(monkeypatch):
    rec = approved_email()
    rec["_submission_intent"] = {"channel": "email", "outbox_id": "outbox-1", "queued_at": "now"}
    store = FakeStore(rec)
    monkeypatch.setattr(submission_runtime, "CampaignReviewStore", lambda _campaign_id: store)
    with pytest.raises(SubmissionRefused):
        submission_runtime.submit_approved("campaign-1", "email", "email-app-1")


def test_email_auditor_rejection_returns_to_review(monkeypatch):
    rec = approved_email()
    store = FakeStore(rec)
    monkeypatch.setattr(submission_runtime, "CampaignReviewStore", lambda _campaign_id: store)
    monkeypatch.setattr(
        submission_runtime.campaign_email,
        "prepare_audited_campaign_email",
        lambda *a, **k: {"queued": False, "audit_status": "rejected", "findings": ["DRAFT_PLACEHOLDER"]},
    )
    result = submission_runtime.submit_approved("campaign-1", "email", "email-app-1")
    assert result["status"] == "needs_review"
    assert result["hold_reason"] == "email_audit_rejected"
    assert store.rec["_state"] == "needs_review"

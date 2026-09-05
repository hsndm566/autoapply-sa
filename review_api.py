#!/usr/bin/env python3
"""Framework-neutral human review service.

The public HTTP service in this repo uses ``http.server`` rather than Flask or
FastAPI. ``ReviewService`` is therefore the stable interface and the service
adapter mounts routes directly around it.
"""
from __future__ import annotations

from typing import Any, Protocol

from draft_review import approve_draft, build_draft, reject_draft
from submit_gate import refusal_reason


class RecordStore(Protocol):
    def list_records(self) -> list[dict[str, Any]]: ...
    def get_record(self, source: str, posting_id: str) -> dict[str, Any] | None: ...
    def save_record(self, rec: dict[str, Any]) -> None: ...


class ReviewService:
    def __init__(self, store: RecordStore, complete=None, profile_loader=None) -> None:
        self.store = store
        self.complete = complete
        self.profile_loader = profile_loader

    def queue(self) -> list[dict[str, Any]]:
        """Return everything requiring human attention, including draftable jobs."""
        records = [
            rec for rec in self.store.list_records()
            if rec.get("_state") in {"path_verified", "drafted", "needs_review"}
        ]
        records.sort(
            key=lambda r: (r.get("_review") or {}).get("at")
            or (r.get("_draft") or {}).get("drafted_at")
            or "",
            reverse=True,
        )
        items: list[dict[str, Any]] = []
        for rec in records:
            draft = rec.get("_draft") or {}
            review = rec.get("_review") or {}
            items.append(
                {
                    "source": rec.get("source"),
                    "posting_id": rec.get("posting_id"),
                    "company": rec.get("company"),
                    "title": rec.get("title"),
                    "location": rec.get("location"),
                    "job_url": rec.get("job_url"),
                    "state": rec.get("_state"),
                    "path": rec.get("_path"),
                    "match_score": draft.get("match_score"),
                    "subject": draft.get("subject"),
                    "cover_letter": draft.get("cover_letter"),
                    "evidence": draft.get("evidence", []),
                    "gaps": draft.get("gaps", []),
                    "cv_highlights": draft.get("cv_highlights", []),
                    "flagged_claims": draft.get("flagged_claims", []),
                    "hold_reason": review.get("reason"),
                    "hold_detail": review.get("detail"),
                    "blocker": refusal_reason(rec),
                }
            )
        return items

    def _require(self, source: str, posting_id: str) -> dict[str, Any]:
        rec = self.store.get_record(source, posting_id)
        if rec is None:
            raise LookupError(f"no record for {source}|{posting_id}")
        return rec

    def draft(self, source: str, posting_id: str, *, lang: str = "en") -> dict[str, Any]:
        if self.complete is None or self.profile_loader is None:
            raise RuntimeError("ReviewService needs complete and profile_loader to draft")
        if lang not in {"en", "ar"}:
            raise ValueError("lang must be 'en' or 'ar'")
        rec = self._require(source, posting_id)
        if rec.get("_state") not in {"path_verified", "needs_review"}:
            raise ValueError(f"cannot draft from state {rec.get('_state')!r}")
        profile = self.profile_loader(rec)
        out = build_draft(rec, profile, self.complete, lang=lang)
        self.store.save_record(out)
        return out

    def approve(
        self,
        source: str,
        posting_id: str,
        *,
        approved_by: str,
        edited_letter: str | None = None,
        edited_subject: str | None = None,
    ) -> dict[str, Any]:
        rec = self._require(source, posting_id)
        out = approve_draft(
            rec,
            approved_by=approved_by,
            edited_letter=edited_letter,
            edited_subject=edited_subject,
        )
        self.store.save_record(out)
        return out

    def reject(
        self,
        source: str,
        posting_id: str,
        *,
        rejected_by: str,
        note: str = "",
    ) -> dict[str, Any]:
        rec = self._require(source, posting_id)
        out = reject_draft(rec, rejected_by=rejected_by, note=note)
        self.store.save_record(out)
        return out


__all__ = ["RecordStore", "ReviewService"]

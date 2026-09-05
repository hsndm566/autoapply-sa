#!/usr/bin/env python3
"""Production wiring for the review service.

Uses the repository's existing Groq configuration and extracts factual candidate
text from the campaign CV. No new model provider is introduced.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

import db
from review_api import ReviewService
from review_store import CampaignReviewStore

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def complete(prompt: str) -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured for review drafting")
    response = requests.post(
        GROQ_ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": os.environ.get("DRAFT_MODEL", DEFAULT_MODEL),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return str(data["choices"][0]["message"]["content"])


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks)[:20000]


def profile_loader(rec: dict[str, Any]) -> dict[str, Any]:
    campaign_id = str(rec.get("_campaign_id") or "").strip()
    campaign = db.get_campaign(campaign_id) if campaign_id else None
    if not campaign:
        raise RuntimeError("campaign not found for review record")
    cv_path = Path(str(campaign.get("cv_path") or ""))
    if not cv_path.is_file():
        raise RuntimeError("campaign CV is not available on the service volume")
    suffix = cv_path.suffix.lower()
    if suffix == ".pdf":
        full_text = _pdf_text(cv_path)
    elif suffix == ".txt":
        full_text = cv_path.read_text(encoding="utf-8", errors="replace")[:20000]
    else:
        raise RuntimeError("review drafting currently requires a PDF or TXT campaign CV")
    if not full_text.strip():
        raise RuntimeError("no factual text could be extracted from the campaign CV")
    return {
        "full_text": full_text,
        "full_name": str(campaign.get("candidate_name") or ""),
        "email": str(campaign.get("candidate_email") or ""),
    }


def service_for_campaign(campaign_id: str) -> ReviewService:
    store = CampaignReviewStore(campaign_id)
    store.sync_campaign_jobs()
    return ReviewService(store=store, complete=complete, profile_loader=profile_loader)


def actor_for_campaign(campaign_id: str) -> str:
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise LookupError("campaign not found")
    email = str(campaign.get("candidate_email") or "").strip().lower()
    return f"campaign:{campaign_id}:{email}"


__all__ = ["actor_for_campaign", "complete", "profile_loader", "service_for_campaign"]

from __future__ import annotations

import os
import re
from typing import Any

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "candidate-profile.yaml")


def load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return loaded if isinstance(loaded, dict) else {}


def _text(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _normalize_platform(value: Any) -> str:
    raw = _text(value)
    aliases = {
        "greenhouse": "greenhouse",
        "greenhouse.io": "greenhouse",
        "ashby": "ashby",
        "ashbyhq": "ashby",
        "lever": "lever",
        "lever.co": "lever",
        "bayt": "bayt.com",
        "bayt.com": "bayt.com",
        "linkedin": "linkedin",
        "linkedin ksa": "linkedin",
        "indeed": "indeed",
        "direct_sa": "direct_sa",
        "direct company page": "direct_sa",
        "company career page": "direct_sa",
        "company career pages": "direct_sa",
        "naukrigulf": "naukrigulf",
        "gulftalent": "gulftalent",
        "jadeer": "jadeer",
        "taqat": "taqat",
        "hirect": "hirect",
        "workday (non-ksa companies)": "workday (non-ksa companies)",
    }
    return aliases.get(raw, raw)


def should_apply(job_title: Any, job_location: Any, platform: Any) -> tuple[bool, str]:
    """Return whether a job is eligible for automatic handling.

    This function is deliberately fail-closed: malformed or unknown inputs never
    become an automatic submission.
    """
    title = _text(job_title)
    location = _text(job_location)
    normalized_platform = _normalize_platform(platform)
    if not title or not location or not normalized_platform:
        return False, "invalid_job_fields"

    config = load_config()
    if not config:
        return False, "missing_policy"

    geo_config = config.get("targeting", {}).get("geography", {})
    if geo_config.get("reject_if_outside_ksa"):
        allowed_terms = [_text(term) for term in geo_config.get("allowed", []) if _text(term)]
        allowed_cities = [_text(city) for city in geo_config.get("cities", []) if _text(city)]
        is_ksa = any(term in location for term in allowed_terms)
        is_city = any(city in location for city in allowed_cities)
        if not (is_ksa or is_city):
            return False, "outside_ksa"

    seniority_config = config.get("targeting", {}).get("seniority", {})
    reject_keywords = [_text(keyword) for keyword in seniority_config.get("reject_title_keywords", []) if _text(keyword)]
    if any(re.search(rf"\b{re.escape(keyword)}\b", title) for keyword in reject_keywords):
        return False, "senior_role"

    portal_config = config.get("targeting", {}).get("portals", {})
    skip_platforms = {_normalize_platform(item) for item in portal_config.get("skip", [])}
    review_platforms = {_normalize_platform(item) for item in portal_config.get("flag_for_manual_review", [])}
    preferred_platforms = {_normalize_platform(item) for item in portal_config.get("preferred", [])}
    preferred_platforms.update({"direct_sa"})

    if normalized_platform in skip_platforms:
        return False, "skipped_platform"
    if normalized_platform in review_platforms:
        return False, "manual_review_platform"
    if normalized_platform not in preferred_platforms:
        return False, "unknown_platform"

    return True, "ok"

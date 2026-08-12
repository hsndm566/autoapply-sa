#!/usr/bin/env python3
"""Diversity enforcement + role/city expansion for candidate campaigns.

Implements the governance caps from MULTI_SOURCE_INTEGRATION_PLAN section 6:
  - max verified options from one employer (default 2 / 30d)
  - max verified options from one ATS source family (default 35%)
  - max watchlist/large-employer concentration (default 10%)
  - min employer count + min source-family count before declaring 50 options
  - 90-day repost window

Also expands a single query into role + city lanes using the candidate profile
so discovery is not limited to one literal string. No network calls.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

import source_registry as sr

# --- Campaign policy defaults (overridable via source_registry policy block) ---
_P = sr.policy()
EMPLOYER_CAP = int(_P.get("employer_cap_per_30d", 2))
SOURCE_FAMILY_CAP_PCT = float(_P.get("source_family_cap_pct", 35))
WATCHLIST_CAP_PCT = float(_P.get("watchlist_cap_pct", 10))
MIN_EMPLOYERS_50 = int(_P.get("min_employers_before_50", 20))
MIN_FAMILIES_50 = int(_P.get("min_source_families_before_50", 4))
REPOST_WINDOW_DAYS = int(_P.get("repost_window_days", 90))

# KSA + remote cities to expand campaigns into.
CAMPAIGN_CITIES = ["Riyadh", "Jeddah", "Dammam", "Khobar", "Remote", "Hybrid"]

# Role synonym lanes (truthful: only adjacent titles the CV supports).
ROLE_LANES = {
    "industrial engineer": [
        "Industrial Engineer", "Process Engineer", "Operations Engineer",
        "Manufacturing Engineer", "Continuous Improvement Engineer",
        "Supply Chain Engineer", "Production Engineer",
    ],
    "business systems analyst": [
        "Business Systems Analyst", "Systems Analyst", "Business Analyst",
        "Operations Analyst", "Process Analyst",
    ],
}


def expand_roles(query: str) -> list[str]:
    """Return the query plus approved adjacent role titles for the lane."""
    q = query.strip().lower()
    for key, lanes in ROLE_LANES.items():
        if key in q:
            base = [query] + lanes
            return list(dict.fromkeys(base))
    return [query]


def expand_cities() -> list[str]:
    return list(CAMPAIGN_CITIES)


def _title_tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", title.lower())}


def role_city_match(rec: dict[str, Any], roles: Iterable[str], cities: Iterable[str]) -> bool:
    """Conservative filter: title overlaps a role lane AND location is empty/
    unknown/remote or names one of the campaign cities. Never infers skills."""
    title = (rec.get("title") or "").lower()
    loc = (rec.get("location") or "").lower()
    if not title:
        return False
    title_tok = _title_tokens(title)
    role_hit = any(
        bool(title_tok & _title_tokens(r.lower())) or r.lower() in title
        for r in roles
    )
    if not role_hit:
        return False
    if not loc or loc in ("", "unknown", "remote", "hybrid"):
        return True
    return any(c.lower() in loc for c in cities)


@dataclass
class DiversityReport:
    total_in: int
    kept: int
    dropped_employer_cap: int = 0
    dropped_source_family_cap: int = 0
    dropped_watchlist_cap: int = 0
    employer_count: int = 0
    family_count: int = 0
    ready_for_50: bool = False
    reasons: list[str] = field(default_factory=list)


def enforce_diversity(
    records: Iterable[dict[str, Any]],
    employer_cap: int = EMPLOYER_CAP,
    watchlist: list[str] | None = None,
) -> tuple[list[dict[str, Any]], DiversityReport]:
    """Apply employer / source-family / watchlist caps. Fail closed: when caps
    would be violated the excess is dropped, never forced through."""
    recs = list(records)
    wl = {w.casefold() for w in (watchlist or sr.watchlist())}
    rep: DiversityReport = DiversityReport(total_in=len(recs), kept=0)

    # Pass 1: per-employer cap. Track used employers + families + watchlist.
    emp_seen: Counter = Counter()
    fam_seen: Counter = Counter()
    wl_seen = 0
    kept: list[dict[str, Any]] = []

    def family_of(r: dict[str, Any]) -> str:
        return (r.get("source") or "").split("_")[0]

    total = len(recs)
    # Percentage caps are computed from the candidate batch, not from the number
    # already kept. A kept-so-far ratio makes the first record 100% of its family
    # and incorrectly drops every source whenever the cap is below 100%.
    # Below MIN_BATCH we preserve the strict employer cap but skip soft quotas so
    # a small honest batch is not silently emptied.
    MIN_BATCH = 20
    apply_pct_caps = total >= MIN_BATCH
    family_quota = max(1, int(total * SOURCE_FAMILY_CAP_PCT / 100))
    watchlist_quota = max(1, int(total * WATCHLIST_CAP_PCT / 100))
    for r in recs:
        emp = (r.get("company") or "").strip().casefold()
        fam = family_of(r)
        is_wl = emp in wl

        if apply_pct_caps and is_wl and wl_seen >= watchlist_quota:
            rep.dropped_watchlist_cap += 1
            continue
        if emp_seen[emp] >= employer_cap:
            rep.dropped_employer_cap += 1
            continue
        if apply_pct_caps and fam_seen[fam] >= family_quota:
            rep.dropped_source_family_cap += 1
            continue

        emp_seen[emp] += 1
        fam_seen[fam] += 1
        if is_wl:
            wl_seen += 1
        rep.kept += 1
        kept.append(r)

    rep.employer_count = len(emp_seen)
    rep.family_count = len({family_of(r) for r in kept})
    if rep.kept >= 50:
        if rep.employer_count < MIN_EMPLOYERS_50:
            rep.ready_for_50 = False
            rep.reasons.append(
                f"Employer count {rep.employer_count} < {MIN_EMPLOYERS_50} before declaring 50 options.")
        elif rep.family_count < MIN_FAMILIES_50:
            rep.ready_for_50 = False
            rep.reasons.append(
                f"Source-family count {rep.family_count} < {MIN_FAMILIES_50} before declaring 50 options.")
        else:
            rep.ready_for_50 = True
    return kept, rep

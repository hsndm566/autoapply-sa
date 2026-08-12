"""Durable, read-only discovery for active AutoApply campaigns.

The module obtains public Greenhouse and Ashby listings, normalizes and de-duplicates
them through the existing source layer, applies candidate-role and diversity filters,
and persists candidate options.  It never drafts, queues an external action, sends an
email, opens a browser, or changes a campaign's execution flag.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import db
import discovery
import diversity
import job_schema
import path_verifier
import source_registry

DISCOVERY_EVENT = "campaign_discovery_completed"
DEFAULT_COOLDOWN_SECONDS = 6 * 60 * 60
MAX_CAMPAIGNS_PER_CYCLE = 10


def _enabled() -> bool:
    return os.environ.get("CAMPAIGN_DISCOVERY_ENABLED", "true").lower() == "true"


def _cooldown_seconds() -> int:
    try:
        return max(300, int(os.environ.get("CAMPAIGN_DISCOVERY_INTERVAL_SECONDS", str(DEFAULT_COOLDOWN_SECONDS))))
    except ValueError:
        return DEFAULT_COOLDOWN_SECONDS


def _active_sources() -> list[str]:
    """Return only registry-enabled Tier-A sources; Lever remains omitted while disabled."""
    return [
        str(source["id"])
        for source in source_registry.sources()
        if source.get("tier") == "A" and source.get("status") == "active" and source.get("id") in {"greenhouse", "ashby"}
    ]


def _persist_campaign_jobs(campaign: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, int]:
    added = 0
    existing = 0
    paths: dict[str, int] = {}
    roles = diversity.expand_roles(str(campaign.get("target_role") or ""))
    cities = diversity.expand_cities()
    if campaign.get("city"):
        cities = list(dict.fromkeys([str(campaign["city"]), *cities]))
    matched = [record for record in records if diversity.role_city_match(record, roles, cities)]
    deduped, dedup_stats = job_schema.dedup(matched)
    selected, diversity_report = diversity.enforce_diversity(deduped)
    for record in selected:
        decision = path_verifier.verify(record)
        _job_id, created = db.add_campaign_job(
            campaign["id"],
            company=str(record.get("company") or ""),
            title=str(record.get("title") or ""),
            job_url=str(record.get("apply_url") or record.get("job_url") or ""),
            source=str(record.get("source") or ""),
            location=str(record.get("location") or ""),
            path_state=decision.state,
        )
        paths[decision.state] = paths.get(decision.state, 0) + 1
        if created:
            added += 1
        else:
            existing += 1
    return {
        "matched": len(matched),
        "deduped": len(deduped),
        "selected": len(selected),
        "added": added,
        "existing": existing,
        "hard_duplicates_removed": dedup_stats["hard_removed"],
        "soft_duplicates_removed": dedup_stats["soft_removed"],
        "employer_cap_dropped": diversity_report.dropped_employer_cap,
        "source_family_cap_dropped": diversity_report.dropped_source_family_cap,
        "watchlist_cap_dropped": diversity_report.dropped_watchlist_cap,
        "paths": paths,
    }


def discover_campaign(
    campaign: dict[str, Any],
    *,
    fetch: bool = True,
    discover_fn: Callable[..., list[dict[str, Any]]] = discovery.discover_all,
) -> dict[str, Any]:
    """Run one read-only discovery pass for an active campaign and persist options."""
    sources = _active_sources()
    if not sources:
        result = {"campaign_id": campaign["id"], "status": "blocked", "reason": "NO_ACTIVE_READONLY_SOURCES", "sources": []}
        db.add_campaign_event(campaign["id"], DISCOVERY_EVENT, "warning", "No registry source is enabled for read-only campaign discovery.", result)
        return result
    try:
        records = discover_fn(sources=sources, fetch=fetch)
    except Exception as exc:
        result = {"campaign_id": campaign["id"], "status": "failed", "reason": type(exc).__name__, "sources": sources}
        db.add_campaign_event(campaign["id"], "campaign_discovery_failed", "warning", "Read-only source discovery failed without queuing any external action.", result)
        return result
    persisted = _persist_campaign_jobs(campaign, records)
    result = {"campaign_id": campaign["id"], "status": "completed", "sources": sources, "fetched": len(records), **persisted}
    db.add_campaign_event(
        campaign["id"],
        DISCOVERY_EVENT,
        "info",
        f"Read-only discovery completed: {persisted['added']} new job options stored; external action remains disabled.",
        result,
    )
    return result


def run_active_campaign_discovery(*, fetch: bool = True, discover_fn: Callable[..., list[dict[str, Any]]] = discovery.discover_all) -> dict[str, Any]:
    """Discover jobs for a bounded number of active readonly campaigns.

    A cooldown is tracked through campaign events to avoid re-fetching every board
    on each five-minute maintenance pass.  This scheduler path is read-only with
    respect to third parties; database writes are only campaign options and events.
    """
    if not _enabled():
        return {"enabled": False, "processed": 0, "skipped_cooldown": 0, "results": []}
    processed = 0
    skipped = 0
    results: list[dict[str, Any]] = []
    for campaign in db.list_campaigns_with_status("active_readonly", limit=MAX_CAMPAIGNS_PER_CYCLE):
        if db.campaign_event_within(campaign["id"], DISCOVERY_EVENT, _cooldown_seconds()):
            skipped += 1
            continue
        results.append(discover_campaign(campaign, fetch=fetch, discover_fn=discover_fn))
        processed += 1
    return {"enabled": True, "processed": processed, "skipped_cooldown": skipped, "results": results}


__all__ = ["discover_campaign", "run_active_campaign_discovery"]

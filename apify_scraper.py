#!/usr/bin/env python3
"""Bounded optional Apify fallback for discovery. Paid execution is off by default."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

import db
import free_scraper

LOG = logging.getLogger("autoapply.apify")
ACTOR_ID = "jpraRc4MCUh5ehbHV"
CACHE_TTL_SECONDS = 6 * 3600
HARD_MAX_PER_RUN_USD, HARD_MAX_DAILY_USD, HARD_MAX_TOTAL_USD = 0.10, 0.25, 1.0
POLL_ATTEMPTS, POLL_SECONDS = 3, 2


def _normalise(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _query(field: object, max_results: object, country: object) -> tuple[str, str, int, str]:
    keyword, region = _normalise(field), _normalise(country) or "saudi arabia"
    if not keyword:
        raise ValueError("field is required")
    try:
        limit = min(max(int(max_results), 1), 100)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_results must be an integer") from exc
    return keyword, region, limit, hashlib.sha256(f"{keyword}|{region}|{limit}".encode()).hexdigest()


def _money(name: str, hard_limit: float) -> float:
    try:
        value = float(os.environ.get(name, "0"))
    except ValueError:
        return 0.0
    return value if 0 < value <= hard_limit else 0.0


def _paid_config() -> tuple[float, float, float] | None:
    if os.environ.get("APIFY_PAID_ENABLED", "false").lower() != "true":
        return None
    if os.environ.get("APIFY_COST_ESTIMATE_REVIEWED", "false").lower() != "true":
        return None
    try:
        estimate = float(os.environ.get("APIFY_COST_ESTIMATE_USD", "0"))
    except ValueError:
        return None
    per_run = _money("APIFY_MAX_COST_PER_RUN_USD", HARD_MAX_PER_RUN_USD)
    daily = _money("APIFY_MAX_COST_DAILY_USD", HARD_MAX_DAILY_USD)
    total = _money("APIFY_MAX_COST_TOTAL_USD", HARD_MAX_TOTAL_USD)
    return (per_run, daily, total) if estimate > 0 and estimate <= per_run and per_run and daily and total else None


def _request_json(url: str, *, data: bytes | None = None) -> dict[str, Any]:
    key = os.environ.get("APIFY_API_KEY", "")
    if not key:
        raise RuntimeError("Apify API key is not configured")
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    response = json.loads(urllib.request.urlopen(request, timeout=30).read())
    return response if isinstance(response, dict) else {}


def _start_actor(keyword: str, region: str, limit: int, cost_cap: float) -> tuple[str, str]:
    # Official API: https://docs.apify.com/api/v2/actors-runs-post documents both caps.
    options = urllib.parse.urlencode({"maxItems": limit, "maxTotalChargeUsd": f"{cost_cap:.2f}"})
    response = _request_json(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?{options}",
        data=json.dumps({"keyword": keyword, "max_results": limit, "country": region}).encode(),
    )
    run = response.get("data") if isinstance(response.get("data"), dict) else {}
    run_id, dataset_id = str(run.get("id") or ""), str(run.get("defaultDatasetId") or "")
    if not run_id or not dataset_id:
        raise RuntimeError("Apify start response missing run or dataset id")
    return run_id, dataset_id


def _run_status(run_id: str) -> str:
    response = _request_json(f"https://api.apify.com/v2/actor-runs/{urllib.parse.quote(run_id, safe='')}")
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    return str(data.get("status") or "").upper()


def _fetch_dataset(dataset_id: str, limit: int) -> list[dict[str, Any]]:
    key = os.environ.get("APIFY_API_KEY", "")
    request = urllib.request.Request(
        f"https://api.apify.com/v2/datasets/{urllib.parse.quote(dataset_id, safe='')}/items?clean=true&limit={limit}",
        headers={"Authorization": f"Bearer {key}"},
    )
    response = json.loads(urllib.request.urlopen(request, timeout=30).read())
    return response if isinstance(response, list) else []


def _jobs(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"company": str(item.get("company_name", item.get("company", "unknown"))), "title": str(item.get("title", "")),
             "id": str(item.get("official_url", item.get("platform_url", ""))), "url": str(item.get("official_url", item.get("platform_url", ""))),
             "description": str(item.get("description", "")), "location": str(item.get("location", ""))}
            for item in items if isinstance(item, dict)]


def scrape(field: str, max_results: int = 100, country: str = "Saudi Arabia", *, free_sources_exhausted: bool = False) -> list[dict[str, Any]]:
    """Return fresh cache/free jobs first; a paid launch is explicit, bounded, and never retried."""
    keyword, region, limit, query_key = _query(field, max_results, country)
    cached = db.get_apify_cache(query_key, CACHE_TTL_SECONDS)
    if cached is not None:
        return cached["jobs"]
    try:
        free_jobs = free_scraper.scrape_field(keyword, location=region, max_results=limit)
    except Exception as exc:
        LOG.warning("free discovery unavailable query=%s error=%s", query_key[:12], type(exc).__name__)
        return []
    if free_jobs:
        db.put_apify_cache(query_key, keyword, region, limit, "free", free_jobs)
        return free_jobs
    # Legacy free adapters swallow some network failures. An empty list is not
    # evidence that equivalent free coverage was successfully exhausted.
    config = _paid_config() if free_sources_exhausted and os.environ.get("APIFY_API_KEY") else None
    if config is None:
        return []
    per_run, daily, total = config
    reserved, _reason = db.reserve_apify_run(query_key, keyword, region, limit, per_run, daily, total)
    if not reserved:
        return []
    try:
        run_id, dataset_id = _start_actor(keyword, region, limit, per_run)
        db.update_apify_reservation(query_key, "started", provider_run_id=run_id)
    except Exception as exc:
        # The provider can accept a request before its response is lost: retain this reservation.
        db.update_apify_reservation(query_key, "uncertain", detail=type(exc).__name__)
        return []
    for _ in range(POLL_ATTEMPTS):
        try:
            status = _run_status(run_id)
        except Exception as exc:
            db.update_apify_reservation(query_key, "uncertain", run_id, type(exc).__name__)
            return []
        if status == "SUCCEEDED":
            try:
                jobs = _jobs(_fetch_dataset(dataset_id, limit))
            except Exception as exc:
                db.update_apify_reservation(query_key, "uncertain", run_id, type(exc).__name__)
                return []
            db.put_apify_cache(query_key, keyword, region, limit, "apify", jobs)
            db.update_apify_reservation(query_key, "succeeded", run_id)
            return jobs
        if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            db.update_apify_reservation(query_key, "failed", run_id, status)
            return []
        time.sleep(POLL_SECONDS)
    db.update_apify_reservation(query_key, "uncertain", run_id, "provider_not_terminal")
    return []

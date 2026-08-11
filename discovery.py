#!/usr/bin/env python3
"""Read-only multi-source discovery adapters (Tier A: Greenhouse, Lever, Ashby).

These adapters only FETCH public job-board listings and normalize them into the
shared ``job_schema`` record. They never: submit, click, authenticate (beyond
public endpoints), spend browser capacity, or call Apify. Live fetch is optional
and guarded: call ``discover_source(..., fetch=True)`` for the read-only canary;
the default path uses injected fixtures.

On any permanent error (404/401) the adapter returns [] (fail closed). Transient
errors (429/5xx/timeout) get bounded exponential backoff, then fail closed. A
per-call log (``clear_fetch_log`` / ``get_fetch_log``) records status + reason +
retries for the canary report.

Corrected endpoints (validated 2026-08-12):
  Greenhouse: https://boards-api.greenhouse.io/v1/boards/{board}/jobs   (HTTP 200)
  Lever:      https://api.lever.co/v0/postings/{client}?mode=json       (HTTP 200 when client exists)
  Ashby:      https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=false
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable

import job_schema as js
import source_registry as sr

UA = {"User-Agent": "Mozilla/5.0 (compatible; AutoApplySA-Discovery/1.0)"}
_FETCHER: Callable[[str], bytes] | None = None  # injectable for tests (fixtures)
_FETCH_LOG: list[dict[str, Any]] = []


def set_fetcher(fetcher: Callable[[str], bytes]) -> None:
    """Inject a deterministic fetcher (file fixture / canned response)."""
    global _FETCHER
    _FETCHER = fetcher


def clear_fetch_log() -> None:
    _FETCH_LOG.clear()


def get_fetch_log() -> list[dict[str, Any]]:
    return list(_FETCH_LOG)


def _fetch_bytes(url: str, timeout: int = 15, max_retries: int = 3) -> tuple[bytes, str | None, int]:
    """Return (data, error_reason, retries). error_reason None on success."""
    if _FETCHER is not None:
        return _FETCHER(url), None, 0
    last_reason: str | None = None
    retries = 0
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(2_000_000), None, retries
        except urllib.error.HTTPError as e:
            # Permanent client/server errors -> do NOT retry (fail closed).
            if e.code in (400, 401, 403, 404, 410):
                return b"", f"HTTP {e.code} {e.reason}", retries
            # 429 / 5xx -> transient, back off and retry.
            time.sleep(2 ** attempt)
            retries += 1
            last_reason = f"HTTP {e.code} {e.reason}"
            continue
        except Exception as e:  # timeout / DNS / TLS -> transient
            time.sleep(2 ** attempt)
            retries += 1
            last_reason = f"{type(e).__name__}: {str(e)[:60]}"
            continue
    return b"", last_reason, retries


def _maybe_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _log(employer: str, url: str, ok: bool, reason: str | None, count: int, retries: int) -> None:
    _FETCH_LOG.append({
        "employer": employer, "url": url, "ok": ok,
        "reason": reason, "count": count, "retries": retries,
    })


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------
def _greenhouse_employer_key(emp: dict[str, Any]) -> str:
    return emp.get("board") or emp.get("company") or emp.get("name", "")


def fetch_greenhouse(employer: dict[str, Any]) -> list[dict[str, Any]]:
    board = _greenhouse_employer_key(employer)
    if not board:
        return []
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=false"
    data, reason, retries = _fetch_bytes(url)
    _log(employer if False else (employer.get("name", board) if isinstance(employer, dict) else board),
         url, ok=(data != b""), reason=reason, count=0, retries=retries)
    parsed = _maybe_json(data)
    if not parsed:
        return []
    out = []
    for j in parsed.get("jobs", []):
        jid = j.get("id")
        if not jid:
            continue
        out.append(js.normalize_job(
            source="greenhouse",
            employer_key=board,
            posting_id=jid,
            company=employer.get("name", board) if isinstance(employer, dict) else board,
            title=j.get("title", ""),
            location=str(j.get("location", "") or ""),
            job_url=f"https://boards.greenhouse.io/{board}/jobs/{jid}",
            apply_url=f"https://boards.greenhouse.io/{board}/jobs/{jid}",
            raw=j,
        ))
    # update count in log entry
    if _FETCH_LOG:
        _FETCH_LOG[-1]["count"] = len(out)
    return out


# ---------------------------------------------------------------------------
# Lever  (corrected: api.lever.co/v0/postings/{client}?mode=json)
# ---------------------------------------------------------------------------
def _lever_employer_key(emp: dict[str, Any]) -> str:
    return emp.get("company") or emp.get("name", "")


def fetch_lever(employer: dict[str, Any]) -> list[dict[str, Any]]:
    # The Lever CLIENT slug is a dedicated field and is NOT assumed to equal the
    # company or org name (fix 4). Fall back through explicit fields.
    client = employer.get("client") or employer.get("board") or employer.get("company") or employer.get("name", "")
    if not client:
        return []
    url = f"https://api.lever.co/v0/postings/{client}?mode=json"
    data, reason, retries = _fetch_bytes(url)
    name = employer.get("name", client) if isinstance(employer, dict) else client
    _log(name, url, ok=(data != b""), reason=reason, count=0, retries=retries)
    parsed = _maybe_json(data)
    if parsed is None:
        return []
    # Lever returns {"data": [...]} with mode=json, or a bare list.
    items = parsed.get("data") if isinstance(parsed, dict) and "data" in parsed else (
        parsed if isinstance(parsed, list) else [])
    out = []
    for j in items:
        jid = j.get("id")
        if not jid:
            continue
        cats = j.get("categories") or {}
        loc = cats.get("location", "") if isinstance(cats, dict) else ""
        # Fix 2: prefer the actual application URL (applyUrl) over the hosted detail page.
        apply = j.get("applyUrl") or j.get("hostedUrl", "")
        out.append(js.normalize_job(
            source="lever",
            employer_key=client,
            posting_id=jid,
            company=name,
            title=j.get("text", ""),
            location=str(loc or ""),
            job_url=j.get("hostedUrl", ""),
            apply_url=apply,
            raw=j,
        ))
    if _FETCH_LOG:
        _FETCH_LOG[-1]["count"] = len(out)
    return out


# ---------------------------------------------------------------------------
# Ashby  (corrected: posting-api/job-board/{board}?includeCompensation=false)
# ---------------------------------------------------------------------------
def _ashby_employer_key(emp: dict[str, Any]) -> str:
    return emp.get("org") or emp.get("name", "")


def _norm_loc(loc: Any) -> str:
    if loc is None:
        return ""
    if isinstance(loc, dict):
        return str(loc.get("location") or loc.get("name") or "")
    return str(loc)


def fetch_ashby(employer: dict[str, Any]) -> list[dict[str, Any]]:
    org = _ashby_employer_key(employer)
    if not org:
        return []
    url = f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=false"
    data, reason, retries = _fetch_bytes(url)
    name = employer.get("name", org) if isinstance(employer, dict) else org
    _log(name, url, ok=(data != b""), reason=reason, count=0, retries=retries)
    parsed = _maybe_json(data)
    if not parsed:
        return []
    out = []
    for j in parsed.get("jobs", []):
        if j.get("isListed") is False:
            continue
        jid = j.get("id")
        if not jid:
            continue
        org_name = j.get("organization")
        if isinstance(org_name, dict):
            org_name = org_name.get("name")
        # Fix 2: prefer the actual application URL (applyUrl) over the job-detail page.
        apply = j.get("applyUrl") or j.get("jobUrl", "")
        out.append(js.normalize_job(
            source="ashby",
            employer_key=org,
            posting_id=jid,
            company=org_name or name,
            title=j.get("title", ""),
            location=_norm_loc(j.get("location")),
            job_url=j.get("jobUrl", ""),
            apply_url=apply,
            raw=j,
        ))
    if _FETCH_LOG:
        _FETCH_LOG[-1]["count"] = len(out)
    return out


_FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def discover_source(source_id: str, fetch: bool = False) -> list[dict[str, Any]]:
    """Discover all employers for one source. Returns records only (fail-closed).

    Honors the GENERAL source ``status`` from the registry: a source whose
    status is not "active" (e.g. Lever while unverified) is skipped entirely.
    No special-case Lever condition — the registry is the single source of truth.
    """
    source = sr.source_by_id(source_id)
    if not source:
        return []
    if source.get("status") != "active":
        return []
    fn = _FETCHERS.get(source_id)
    if fn is None:
        return []
    records: list[dict[str, Any]] = []
    for emp in sr.employers_for_source(source_id):
        try:
            if fetch:
                records.extend(fn(emp))
            else:
                # No fetcher injected and fetch=False -> read-only no-op.
                if _FETCHER is None:
                    continue
                records.extend(fn(emp))
        except Exception:
            continue
    return records


def discover_all(sources: Iterable[str] | None = None, fetch: bool = False) -> list[dict[str, Any]]:
    """Registry-driven discovery across Tier A sources. No hard-coded boards."""
    ids = list(sources) if sources else [s["id"] for s in sr.sources() if s.get("tier") == "A"]
    out: list[dict[str, Any]] = []
    for sid in ids:
        out.extend(discover_source(sid, fetch=fetch))
    return out

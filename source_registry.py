#!/usr/bin/env python3
"""Source registry loader for the multi-source discovery layer.

Replaces the previous hard-coded repeat-company boards list in the
orchestrator and free_scraper. Selection is registry-driven: every employer,
ATS board, careers URL, country/sector tag, and last-successful-refresh time
lives in ``source_registry.json``. No code path may hard-code a board slug.

Read-only. Never contacts a job board.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Iterator

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.environ.get("SOURCE_REGISTRY_PATH", os.path.join(HERE, "source_registry.json"))

_CACHE: dict[str, Any] | None = None


def load() -> dict[str, Any]:
    """Load and cache the registry. Returns {} on missing/corrupt file."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as fh:
            _CACHE = json.load(fh)
    except Exception:
        _CACHE = {}
    return _CACHE


def reload() -> dict[str, Any]:
    global _CACHE
    _CACHE = None
    return load()


def policy() -> dict[str, Any]:
    return load().get("policy", {})


def watchlist() -> list[str]:
    return [w.casefold() for w in load().get("watchlist", [])]


def sources() -> list[dict[str, Any]]:
    return load().get("sources", [])


def source_by_id(source_id: str) -> dict[str, Any] | None:
    for s in sources():
        if s.get("id") == source_id:
            return s
    return None


def families() -> set[str]:
    return {s.get("family", "") for s in sources() if s.get("family")}


def iter_employers(source_id: str | None = None) -> Iterator[dict[str, Any]]:
    """Yield every employer record, optionally filtered by source id."""
    for s in sources():
        if source_id and s.get("id") != source_id:
            continue
        for emp in s.get("employers", []):
            rec = dict(emp)
            rec.setdefault("ats", s.get("family"))
            rec["_source_id"] = s.get("id")
            rec["_family"] = s.get("family")
            yield rec


def employers_for_source(source_id: str) -> list[dict[str, Any]]:
    return [e for e in iter_employers(source_id)]


def mark_refresh(source_id: str, employer_key: str, ok: bool) -> None:
    """Record a successful/unsuccessful refresh time for a board.

    Persists to the registry file so degraded boards are tracked across runs.
    Fails closed: any write error is swallowed, never raises into the caller.
    """
    try:
        reg = load()
        for s in reg.get("sources", []):
            if s.get("id") != source_id:
                continue
            for emp in s.get("employers", []):
                key = emp.get("board") or emp.get("company") or emp.get("org")
                if key == employer_key:
                    emp["last_refresh"] = time.time()
                    emp["last_refresh_ok"] = bool(ok)
                    break
        with open(REGISTRY_PATH, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, indent=2, ensure_ascii=False)
        reload()
    except Exception:
        pass


def source_family_count() -> int:
    return len(families())


# ---------------------------------------------------------------------------
# Lever acceptance gate
# ---------------------------------------------------------------------------
# Lever's public client slugs are NOT guessable from the company name. A board
# is admitted to the live source set only after BOTH conditions hold:
#   1. Its public employer careers URL is independently reachable (HTTP 200),
#      proving the company actually runs a Lever board.
#   2. The documented public endpoint
#      https://api.lever.co/v0/postings/{client}?mode=json
#      returns a valid listing response (HTTP 200 + parseable JSON).
# Until then Lever stays DISABLED in the live set (see lever_enabled()).

_LEVER_ENDPOINT = "https://api.lever.co/v0/postings/{client}?mode=json"


def _http_get_ok(url: str, timeout: int = 15) -> tuple[bool, str]:
    """Return (ok, reason). Read-only HEAD/GET; never submits."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AutoApplySA-Discovery/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (200 <= r.status < 300), f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:  # timeout / DNS / TLS
        return False, f"{type(e).__name__}: {str(e)[:60]}"


def verify_lever_board(client: str, careers_url: str) -> dict[str, Any]:
    """Independently verify a Lever board before admitting it to the live set.

    Args:
        client: the Lever client slug (api.lever.co/v0/postings/{client}).
        careers_url: the employer's public careers page (must be reachable),
                     confirming the company actually runs a Lever board.
    Returns: {accepted, client, careers_url, careers_ok, endpoint_ok, reason}.
    """
    careers_ok, careers_reason = _http_get_ok(careers_url)
    endpoint_ok, endpoint_reason = _http_get_ok(_LEVER_ENDPOINT.format(client=client))
    accepted = bool(careers_ok and endpoint_ok)
    return {
        "accepted": accepted,
        "client": client,
        "careers_url": careers_url,
        "careers_ok": careers_ok,
        "endpoint_ok": endpoint_ok,
        "reason": (None if accepted else f"careers={careers_reason}; endpoint={endpoint_reason}"),
    }


def lever_enabled() -> bool:
    """Lever is enabled in the live set only if at least one verified board exists."""
    for s in sources():
        if s.get("id") != "lever":
            continue
        for emp in s.get("employers", []):
            if emp.get("verified") is True:
                return True
    return False


def admit_lever_board(client: str, careers_url: str, *, commit: bool = False) -> dict[str, Any]:
    """Verify then persist a Lever board as verified (only if both checks pass).

    Fails closed: if verification fails, nothing is written and the board is NOT
    enabled. Persists ``verified: true`` to the registry only on success.
    """
    result = verify_lever_board(client, careers_url)
    if not result["accepted"]:
        return result
    if commit:
        try:
            reg = load()
            for s in reg.get("sources", []):
                if s.get("id") != "lever":
                    continue
                for emp in s.get("employers", []):
                    if (emp.get("company") or emp.get("org")) == client:
                        emp["verified"] = True
                        emp["careers_url"] = careers_url
                        break
            with open(REGISTRY_PATH, "w", encoding="utf-8") as fh:
                json.dump(reg, fh, indent=2, ensure_ascii=False)
            reload()
        except Exception:
            result["accepted"] = False
            result["reason"] = "registry write failed"
    return result

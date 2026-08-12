"""Read-only portal change detection for AutoApply SA.

The sentinel fetches one already-discovered public job URL per source at a bounded
interval and derives a privacy-minimized semantic form fingerprint.  It never opens
a browser, uploads a CV, fills an input, clicks a control, queues work, or changes a
source into an execution-capable state.
"""
from __future__ import annotations

import hashlib
import html.parser
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import db

ADAPTER_ID = "portal_sentinel_http_v1"
ADAPTER_VERSION = "1.0.0"
MAX_BODY_BYTES = 1_000_000
_ALLOWED_HOSTS = {
    "greenhouse": {"boards.greenhouse.io", "job-boards.greenhouse.io"},
    "ashby": {"jobs.ashbyhq.com"},
    "lever": {"jobs.lever.co"},
}
_BLOCKER_RE = re.compile(r"\b(captcha|recaptcha|hcaptcha|sign in|log in|login required)\b", re.I)


@dataclass(frozen=True)
class ProbeResult:
    source: str
    target_url: str
    status: str
    fingerprint: str = ""
    previous_fingerprint: str = ""
    observation: dict[str, Any] | None = None
    error_code: str = ""
    probe_id: str = ""


class _FormShapeParser(html.parser.HTMLParser):
    """Extract only structural control semantics, never application values/text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.form_count = 0
        self.controls: list[tuple[str, str, bool]] = []
        self.file_input_count = 0
        self.required_control_count = 0
        self._body_markers: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        attr = {str(key).lower(): str(value or "") for key, value in attrs}
        if lowered_tag == "form":
            self.form_count += 1
        if lowered_tag not in {"input", "select", "textarea"}:
            return
        control_type = attr.get("type", "text").lower() if lowered_tag == "input" else lowered_tag
        required = "required" in attr or attr.get("aria-required", "").lower() == "true"
        semantic = (lowered_tag, control_type, required)
        self.controls.append(semantic)
        if control_type == "file":
            self.file_input_count += 1
        if required:
            self.required_control_count += 1

    def handle_data(self, data: str) -> None:
        # A bounded token-only blocker scan is enough; no text is retained.
        if len(self._body_markers) < 32:
            match = _BLOCKER_RE.search(data)
            if match:
                self._body_markers.append(match.group(1).lower())

    def observation(self) -> dict[str, Any]:
        signature = sorted(f"{tag}:{kind}:{int(required)}" for tag, kind, required in self.controls)
        return {
            "form_count": self.form_count,
            "control_count": len(signature),
            "file_input_count": self.file_input_count,
            "required_control_count": self.required_control_count,
            "control_shape_digest": hashlib.sha256("|".join(signature).encode("utf-8")).hexdigest(),
            "blocker_markers": sorted(set(self._body_markers)),
        }


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def _source_url_allowed(source: str, url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in _ALLOWED_HOSTS.get(source, set())


def _fetch_html(url: str, timeout: int) -> tuple[int, str]:
    request = Request(
        url,
        headers={"User-Agent": "AutoApplySA-PortalSentinel/1.0 (+read-only-health-check)"},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        status = int(getattr(response, "status", 200))
        raw = response.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    return status, raw.decode("utf-8", "replace")


def _fingerprint(source: str, observation: dict[str, Any]) -> str:
    material = {
        "source": source,
        "adapter": ADAPTER_ID,
        "version": ADAPTER_VERSION,
        "form_count": observation["form_count"],
        "control_count": observation["control_count"],
        "file_input_count": observation["file_input_count"],
        "required_control_count": observation["required_control_count"],
        "control_shape_digest": observation["control_shape_digest"],
        "blocker_markers": observation["blocker_markers"],
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def probe_source(
    source: str,
    target_url: str,
    *,
    fetcher: Callable[[str, int], tuple[int, str]] = _fetch_html,
    force: bool = False,
) -> ProbeResult:
    """Record one read-only source observation and report stable/drifted state."""
    source = source.strip().lower()
    if not _source_url_allowed(source, target_url):
        return _persist(source, target_url, "blocked", error_code="UNSAFE_OR_UNSUPPORTED_SOURCE_URL")
    previous = db.latest_portal_probe(source)
    interval = _bounded_int("PORTAL_PROBE_INTERVAL_SECONDS", 21600, 300, 604800)
    now = time.time()
    if not force and previous and now - float(previous.get("observed_at") or 0) < interval:
        return ProbeResult(
            source=source, target_url=target_url, status="cooldown", fingerprint=str(previous.get("fingerprint") or ""),
            previous_fingerprint=str(previous.get("previous_fingerprint") or ""), observation=previous.get("observation") or {},
        )
    try:
        status_code, body = fetcher(target_url, _bounded_int("PORTAL_PROBE_TIMEOUT_SECONDS", 12, 3, 30))
    except HTTPError as exc:
        return _persist(source, target_url, "unavailable", error_code=f"HTTP_{exc.code}")
    except URLError:
        return _persist(source, target_url, "unavailable", error_code="NETWORK_ERROR")
    except ValueError as exc:
        return _persist(source, target_url, "blocked", error_code=str(exc))
    except Exception as exc:  # no raw exception details are persisted
        return _persist(source, target_url, "unavailable", error_code=f"FETCH_{type(exc).__name__}")
    if status_code < 200 or status_code >= 400:
        return _persist(source, target_url, "unavailable", error_code=f"HTTP_{status_code}")
    parser = _FormShapeParser()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        return _persist(source, target_url, "blocked", error_code="HTML_PARSE_FAILED")
    observation = parser.observation()
    fingerprint = _fingerprint(source, observation)
    if observation["blocker_markers"]:
        return _persist(source, target_url, "blocked", fingerprint=fingerprint, observation=observation, error_code="PORTAL_BLOCKER_DETECTED")
    prior_fingerprint = str(previous.get("fingerprint") or "") if previous else ""
    status = "baseline" if not prior_fingerprint else ("stable" if prior_fingerprint == fingerprint else "drifted")
    return _persist(
        source, target_url, status, fingerprint=fingerprint, previous_fingerprint=prior_fingerprint, observation=observation,
        error_code="PORTAL_FORM_FINGERPRINT_CHANGED" if status == "drifted" else "",
    )


def _persist(
    source: str,
    target_url: str,
    status: str,
    *,
    fingerprint: str = "",
    previous_fingerprint: str = "",
    observation: dict[str, Any] | None = None,
    error_code: str = "",
) -> ProbeResult:
    probe_id = db.record_portal_probe(
        source=source, adapter_id=ADAPTER_ID, adapter_version=ADAPTER_VERSION, target_url=target_url,
        status=status, fingerprint=fingerprint, previous_fingerprint=previous_fingerprint,
        observation=observation, error_code=error_code,
    )
    source_health = "healthy" if status in {"baseline", "stable"} else status
    db.record_source_health(source, source_health, error_code or None)
    return ProbeResult(
        source=source, target_url=target_url, status=status, fingerprint=fingerprint,
        previous_fingerprint=previous_fingerprint, observation=observation or {}, error_code=error_code, probe_id=probe_id,
    )


def run_registered_probes(sources: list[str], *, fetcher: Callable[[str, int], tuple[int, str]] = _fetch_html) -> dict[str, Any]:
    """Run at most one safe probe per supplied source; no application action exists."""
    if os.environ.get("PORTAL_SENTINEL_ENABLED", "true").lower() != "true":
        return {"enabled": False, "probed": 0, "skipped": 0, "results": []}
    results: list[dict[str, Any]] = []
    skipped = 0
    for source in sorted(set(sources)):
        target = db.select_portal_probe_target(source)
        if not target:
            skipped += 1
            continue
        result = probe_source(source, str(target["job_url"]), fetcher=fetcher)
        result_data = {
            "source": result.source, "status": result.status, "error_code": result.error_code,
            "fingerprint": result.fingerprint, "probe_id": result.probe_id,
        }
        results.append(result_data)
        if result.status in {"drifted", "blocked", "unavailable"}:
            db.add_campaign_event(
                str(target["campaign_id"]),
                "portal_source_probe_held",
                "warning",
                "Read-only portal sentinel held the source after an observed change or blocker; no portal action was attempted.",
                result_data,
            )
    return {
        "enabled": True,
        "probed": len(results),
        "skipped": skipped,
        "results": results,
        "external_execution": "disabled",
    }


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "ProbeResult", "probe_source", "run_registered_probes"]

#!/usr/bin/env python3
"""Technical-only synthetic check for AutoApply SA dashboard authentication.

This monitor never reads candidate records, sends application emails, accesses a
CV, or invokes the application dispatcher. It checks the public dashboard route
and Clerk bootstrap endpoint, emits a redacted Sentry event on a status
transition, and sends a minimal owner alert through the repository's existing
Brevo Actions secret.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

DASHBOARD_URL = "https://dashboard.hsndm.tech/"
CLERK_BOOTSTRAP_URL = "https://clerk.hsndm.tech/v1/environment?__clerk_api_version=2025-11-10&__clerk_js_version=5.127.2"
SENTRY_CONFIG_URL = "https://www.hsndm.tech/api/client-config/sentry"
STATE_PATH = Path("monitor-state/dashboard-auth.json")
OWNER_EMAIL = "hasanadam506@gmail.com"
TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class MonitorResult:
    status: str
    readiness_status: int | None
    clerk_bootstrap_status: int | None


def request_status(url: str, headers: dict[str, str] | None = None) -> int | None:
    try:
        return requests.get(url, timeout=TIMEOUT_SECONDS, headers=headers or {}).status_code
    except requests.RequestException:
        return None


def evaluate() -> MonitorResult:
    # The dashboard is a browser route. The old monitor incorrectly probed
    # /healthz/auth on www.hsndm.tech, which is the static marketing host and
    # therefore returned 404 even when the dashboard application was healthy.
    dashboard = request_status(DASHBOARD_URL)
    clerk = request_status(
        CLERK_BOOTSTRAP_URL,
        {
            "Accept": "application/json",
            "Origin": "https://dashboard.hsndm.tech",
            "Referer": "https://dashboard.hsndm.tech/",
        },
    )
    status = "healthy" if dashboard == 200 and clerk is not None and 200 <= clerk < 300 else "degraded"
    return MonitorResult(status=status, readiness_status=dashboard, clerk_bootstrap_status=clerk)


def load_previous_status(path: Path = STATE_PATH) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("status") if isinstance(payload.get("status"), str) else None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def persist(result: MonitorResult, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**asdict(result), "updated_at": int(time.time())}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def technical_text(result: MonitorResult, recovered: bool) -> str:
    state = "recovered" if recovered else "requires attention"
    dashboard = "network-error" if result.readiness_status is None else f"http-{result.readiness_status}"
    clerk = "network-error" if result.clerk_bootstrap_status is None else f"http-{result.clerk_bootstrap_status}"
    return "\n".join(
        [
            f"AutoApply SA dashboard authentication {state}.",
            "Monitor: dashboard-auth",
            f"Dashboard route: {dashboard}",
            f"Clerk bootstrap: {clerk}",
            "This operational alert contains technical status only.",
        ]
    )


def sentry_envelope_url(dsn: str) -> str | None:
    parsed = urlparse(dsn)
    project_id = parsed.path.strip("/").split("/")[-1]
    if not parsed.scheme or not parsed.hostname or not parsed.username or not project_id:
        return None
    return f"{parsed.scheme}://{parsed.hostname}/api/{project_id}/envelope/?sentry_version=7&sentry_key={parsed.username}&sentry_client=autoapply-auth-monitor/1.0"


def report_sentry(result: MonitorResult, recovered: bool) -> bool:
    try:
        config = requests.get(SENTRY_CONFIG_URL, timeout=TIMEOUT_SECONDS).json()
        dsn = config.get("dsn") if isinstance(config, dict) else None
        endpoint = sentry_envelope_url(dsn) if isinstance(dsn, str) else None
        if not endpoint:
            return False
        dashboard = "network-error" if result.readiness_status is None else f"http-{result.readiness_status}"
        clerk = "network-error" if result.clerk_bootstrap_status is None else f"http-{result.clerk_bootstrap_status}"
        event = {
            "event_id": uuid.uuid4().hex,
            "timestamp": int(time.time()),
            "level": "info" if recovered else "error",
            "logger": "autoapply.auth-monitor",
            "message": "Dashboard authentication dependency recovered" if recovered else "Dashboard authentication dependency degraded",
            "platform": "python",
            "tags": {"monitor": "dashboard-auth", "privacy": "technical-only", "dashboard_route": dashboard, "clerk_bootstrap": clerk},
        }
        envelope = f"{json.dumps({'dsn': dsn})}\n{json.dumps({'type': 'event'})}\n{json.dumps(event)}\n"
        return requests.post(endpoint, data=envelope, headers={"Content-Type": "application/x-sentry-envelope"}, timeout=TIMEOUT_SECONDS).ok
    except requests.RequestException:
        return False


def alert_owner(result: MonitorResult, recovered: bool, api_key: str | None = None) -> bool:
    key = api_key or os.environ.get("BREVO_API_KEY")
    if not key:
        return False
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": key, "content-type": "application/json", "accept": "application/json"},
            json={
                "sender": {"email": "apply@hsndm.tech", "name": "AutoApply SA Monitoring"},
                "to": [{"email": OWNER_EMAIL}],
                "subject": "[AutoApply SA] Dashboard auth recovered" if recovered else "[AutoApply SA] Dashboard auth requires attention",
                "textContent": technical_text(result, recovered),
            },
            timeout=TIMEOUT_SECONDS,
        )
        return response.ok
    except requests.RequestException:
        return False


def main() -> int:
    result = evaluate()
    previous = load_previous_status()
    changed = previous is not None and previous != result.status
    initial_degraded = previous is None and result.status == "degraded"
    notified = False
    sentry_reported = False
    if changed or initial_degraded:
        recovered = result.status == "healthy"
        sentry_reported = report_sentry(result, recovered)
        notified = alert_owner(result, recovered)
    persist(result)
    print(json.dumps({"status": result.status, "changed": changed, "sentry_reported": sentry_reported, "owner_alerted": notified}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

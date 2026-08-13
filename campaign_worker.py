"""Safe autonomous worker for AutoApply SA.

The worker is intentionally conservative. It performs deterministic maintenance,
records source/service health, recovers stale queue leases, and makes bounded
read-only calls to public job-board listing APIs for active campaigns. Its audited
email dispatcher remains disabled until separately configured, and it never submits
portal forms. Every email side effect rechecks a current Auditor approval token.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import bayt_profile_adapter
import campaign_discovery
import db
import email_dispatcher
import email_preparation
import portal_sentinel

LOG = logging.getLogger("campaign_worker")
SOURCE_REGISTRY = Path(__file__).with_name("source_registry.json")


def _registry_sources() -> list[str]:
    try:
        data = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8"))
        return sorted({str(item.get("id") or item.get("source") or "").strip() for item in data.get("sources", []) if item.get("id") or item.get("source")})
    except Exception as exc:  # source health must not crash the worker
        LOG.warning("source registry unavailable: %s", exc)
        return []


def run_maintenance_cycle(*, discover_campaigns: bool = True) -> dict[str, object]:
    """Run safe maintenance; optional discovery uses only public listing APIs."""
    db.initialize()
    released = db.recover_stale_outbox()
    db.record_service_health("database", "healthy", "SQLite schema initialized and writable")
    db.record_service_health("auditor_gate", "healthy", "External execution remains fail-closed until Auditor approval")
    db.record_service_health("external_execution", "disabled", "No source-specific upload proof is enabled")
    try:
        bayt = bayt_profile_adapter.queue_summary(db.DB_PATH)
        bayt_state = "browser_handoff_ready" if bayt.get("profile_ready") else "waiting_for_profile"
        db.record_service_health("bayt_profile_handoff", bayt_state, f"total_bayt_leads={bayt.get('total_bayt_leads', 0)}; execution_mode={bayt.get('execution_mode')}")
    except Exception as exc:
        db.record_service_health("bayt_profile_handoff", "degraded", type(exc).__name__)

    registry_sources = _registry_sources()
    for source in registry_sources:
        db.ensure_source_health(source, "configured")

    # Campaign discovery only reads public ATS listing APIs and writes durable job
    # options/events. It cannot queue an email or submit a portal application.
    discovery_result = (
        campaign_discovery.run_active_campaign_discovery(fetch=True)
        if discover_campaigns
        else {"enabled": True, "processed": 0, "skipped_cooldown": 0, "results": [], "deferred": True}
    )
    db.record_service_health(
        "campaign_discovery",
        "healthy" if discovery_result.get("enabled") else "disabled",
        f"processed={discovery_result.get('processed', 0)} skipped_cooldown={discovery_result.get('skipped_cooldown', 0)}",
    )
    # The sentinel only performs bounded HTTP GET observations against already
    # discovered URLs. It has no browser, CV, outbox, or submit interface.
    sentinel_result = portal_sentinel.run_registered_probes(registry_sources)
    db.record_service_health(
        "portal_sentinel",
        "healthy" if sentinel_result.get("enabled") else "disabled",
        f"probed={sentinel_result.get('probed', 0)} skipped={sentinel_result.get('skipped', 0)} external_execution=disabled",
    )
    try:
        preparation_limit = max(1, min(20, int(os.environ.get("EMAIL_PREPARATION_MAX_PER_CYCLE", "10"))))
    except ValueError:
        preparation_limit = 10
    try:
        preparation_result = email_preparation.prepare_pending_batch(limit=preparation_limit)
        db.record_service_health(
            "audited_email_preparation",
            "healthy",
            f"mode=preparation_only selected={preparation_result.get('selected_count', 0)} cv_sha256={preparation_result.get('cv', {}).get('sha256', '')[:12]}",
        )
    except Exception as exc:
        preparation_result = {"ok": False, "error": type(exc).__name__}
        db.record_service_health("audited_email_preparation", "degraded", type(exc).__name__)

    try:
        email_limit = max(1, min(10, int(os.environ.get("EMAIL_OUTREACH_MAX_PER_CYCLE", "5"))))
    except ValueError:
        email_limit = 5
    email_result = email_dispatcher.dispatch_pending(limit=email_limit)
    email_status = "healthy" if email_result.get("enabled") and "configuration" not in email_result else "disabled"
    db.record_service_health(
        "audited_email_dispatcher",
        email_status,
        f"claimed={email_result.get('claimed', 0)} enabled={email_result.get('enabled', False)}",
    )
    result = {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "released_stale_outbox": released,
        "configured_sources": registry_sources,
        "campaign_discovery": discovery_result,
        "portal_sentinel": sentinel_result,
        "email_preparation": preparation_result,
        "email_dispatch": email_result,
        "external_execution": "disabled",
    }
    LOG.info("safe maintenance complete: %s", result)
    return result


def main() -> None:
    interval = max(60, int(os.environ.get("WORKER_INTERVAL_SECONDS", "300")))
    LOG.info("safe campaign worker started | interval_seconds=%s", interval)
    while True:
        try:
            run_maintenance_cycle()
        except Exception as exc:  # one failed maintenance pass must not kill the worker
            LOG.exception("maintenance cycle failed: %s", exc)
            try:
                db.record_service_health("worker", "degraded", str(exc))
            except Exception:
                pass
        time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    main()

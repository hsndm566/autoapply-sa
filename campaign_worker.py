"""Safe autonomous worker for AutoApply SA.

The worker is intentionally conservative.  It performs deterministic maintenance,
records source/service health, and recovers stale queue leases.  It does not send
email or submit portal forms.  Any future dispatcher must verify an Auditor approval
token immediately before an external side effect.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import db

LOG = logging.getLogger("campaign_worker")
SOURCE_REGISTRY = Path(__file__).with_name("source_registry.json")


def _registry_sources() -> list[str]:
    try:
        data = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8"))
        return sorted({str(item.get("id") or item.get("source") or "").strip() for item in data.get("sources", []) if item.get("id") or item.get("source")})
    except Exception as exc:  # source health must not crash the worker
        LOG.warning("source registry unavailable: %s", exc)
        return []


def run_maintenance_cycle() -> dict[str, object]:
    """Run only idempotent, no-network maintenance work."""
    db.initialize()
    released = db.recover_stale_outbox()
    db.record_service_health("database", "healthy", "SQLite schema initialized and writable")
    db.record_service_health("auditor_gate", "healthy", "External execution remains fail-closed until Auditor approval")
    db.record_service_health("external_execution", "disabled", "No source-specific upload proof is enabled")

    for source in _registry_sources():
        db.record_source_health(source, "configured")

    result = {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "released_stale_outbox": released,
        "configured_sources": _registry_sources(),
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

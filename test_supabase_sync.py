"""Manually invoke one development-only accepted-send ledger synchronization.

This script does not call any email transport. It only asks the server-only
Supabase helper to record a supplied accepted-send fact when GitHub Actions
provides the development credentials as environment variables.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from supabase_delivery_sync import sync_accepted_application


def environment_is_configured() -> bool:
    return bool(
        os.environ.get("SUPABASE_DEV_URL", "").strip()
        and os.environ.get("SUPABASE_DEV_SERVICE_ROLE_KEY", "").strip()
    )


async def main() -> int:
    if not environment_is_configured():
        print(json.dumps({"synced": False, "reason": "missing_development_supabase_environment"}, sort_keys=True))
        return 1

    result = await sync_accepted_application(
        external_application_id="test-sync-001",
        external_client_id=3,
        sender_email="apply2@hsndm.tech",
        recipient_email="autoapply-dev-test@example.test",
        company="Test Company",
        role="Test Role",
        city="Riyadh",
        provider_message_id="test-message-001",
        sent_at=datetime.now(timezone.utc).isoformat(),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("synced") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

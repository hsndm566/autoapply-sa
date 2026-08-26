"""Server-only synchronization of accepted email-delivery facts to Supabase.

This module is deliberately usable only by trusted backend code. It derives the
candidate from the active delivery-client mapping instead of trusting a browser
or portal caller, hashes recipient addresses before persistence, and never logs
credential values or recipient addresses.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


LOGGER = logging.getLogger(__name__)
SCHEMA = "autoapply_baseline"
PROVIDER = "brevo"


@dataclass(frozen=True)
class DeliverySyncResult:
    """A non-throwing result for the sender to record without stopping delivery."""

    status: str
    application_id: str | None = None
    reason: str | None = None

    @property
    def synced(self) -> bool:
        return self.status == "synced"


def hash_recipient_email(recipient_email: str) -> str:
    """Normalize and hash an email address before it crosses the ledger boundary."""
    normalized = recipient_email.strip().casefold()
    if not normalized:
        raise ValueError("recipient_email is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _first_row(response: Any) -> Mapping[str, Any] | None:
    data = getattr(response, "data", None)
    if isinstance(data, Mapping):
        return data
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        return data[0]
    return None


def _server_client() -> Any | None:
    url = os.environ.get("SUPABASE_DEV_URL", "").strip()
    service_role_key = os.environ.get("SUPABASE_DEV_SERVICE_ROLE_KEY", "").strip()
    if not url or not service_role_key:
        LOGGER.warning("Supabase delivery sync skipped because development server credentials are not configured")
        return None
    try:
        from supabase import create_client

        return create_client(url, service_role_key)
    except Exception as error:
        LOGGER.warning("Supabase delivery sync client initialization failed (%s)", type(error).__name__)
        return None


def _mapping_candidate_id(client: Any, external_client_id: int, sender_email: str) -> str | None:
    """Resolve the candidate from an active mapping, preferring the stable client ID."""
    table = client.schema(SCHEMA).table("delivery_client_mappings")
    response = (
        table.select("candidate_id")
        .eq("external_client_id", external_client_id)
        .eq("active", True)
        .limit(1)
        .execute()
    )
    row = _first_row(response)
    if row and str(row.get("candidate_id") or "").strip():
        return str(row["candidate_id"])

    response = (
        client.schema(SCHEMA)
        .table("delivery_client_mappings")
        .select("candidate_id")
        .eq("sender_email", sender_email.strip().casefold())
        .eq("active", True)
        .limit(1)
        .execute()
    )
    row = _first_row(response)
    if row and str(row.get("candidate_id") or "").strip():
        return str(row["candidate_id"])
    return None


def _application_id_from_response(client: Any, external_application_id: str, response: Any) -> str | None:
    row = _first_row(response)
    if row and str(row.get("id") or "").strip():
        return str(row["id"])

    lookup = (
        client.schema(SCHEMA)
        .table("email_applications")
        .select("id")
        .eq("external_application_id", external_application_id)
        .limit(1)
        .execute()
    )
    row = _first_row(lookup)
    if row and str(row.get("id") or "").strip():
        return str(row["id"])
    return None


def sync_accepted_delivery(
    *,
    candidate_id: str | None,
    external_application_id: str,
    external_client_id: int,
    sender_email: str,
    recipient_email: str,
    company: str,
    role: str,
    city: str | None,
    delivery_channel: str,
    provider_message_id: str | None,
    send_status: str,
    sent_at: datetime | str,
    provider: str = PROVIDER,
    client: Any | None = None,
) -> DeliverySyncResult:
    """Upsert a mapping-backed accepted send and its idempotent initial event.

    ``candidate_id`` is accepted only as a consistency check. The active mapping is
    always the authority; missing mappings and all errors return a result rather
    than interrupting the scheduled sender or its CSV dedupe fallback.
    """
    external_application_id = external_application_id.strip()
    sender_email = sender_email.strip().casefold()
    if send_status != "accepted":
        return DeliverySyncResult("skipped_non_accepted", reason="only accepted sends may be synchronized")
    if not external_application_id or not sender_email or not company.strip() or not role.strip():
        return DeliverySyncResult("skipped_invalid_input", reason="accepted send record is incomplete")

    database = client or _server_client()
    if database is None:
        return DeliverySyncResult("skipped_unconfigured", reason="development Supabase server credentials are unavailable")

    try:
        mapped_candidate_id = _mapping_candidate_id(database, external_client_id, sender_email)
        if mapped_candidate_id is None:
            LOGGER.warning(
                "Supabase delivery sync skipped because no active client mapping exists for external client %s",
                external_client_id,
            )
            return DeliverySyncResult("skipped_mapping_missing", reason="no active delivery client mapping")
        if candidate_id and candidate_id != mapped_candidate_id:
            LOGGER.warning(
                "Supabase delivery sync skipped because the supplied candidate does not match the active client mapping"
            )
            return DeliverySyncResult("skipped_candidate_mismatch", reason="candidate does not match active mapping")

        sent_at_value = sent_at.isoformat() if isinstance(sent_at, datetime) else str(sent_at).strip()
        if not sent_at_value:
            return DeliverySyncResult("skipped_invalid_input", reason="sent_at is required")
        message_id = (provider_message_id or "").strip() or None
        application_response = (
            database.schema(SCHEMA)
            .table("email_applications")
            .upsert(
                {
                    "candidate_id": mapped_candidate_id,
                    "external_application_id": external_application_id,
                    "external_client_id": external_client_id,
                    "sender_email": sender_email,
                    "recipient_email_hash": hash_recipient_email(recipient_email),
                    "company": company.strip(),
                    "role": role.strip(),
                    "city": city.strip() if city else None,
                    "delivery_channel": delivery_channel.strip() or "email",
                    "provider_message_id": message_id,
                    "send_status": "accepted",
                    "sent_at": sent_at_value,
                    "last_activity_at": sent_at_value,
                },
                on_conflict="external_application_id",
            )
            .execute()
        )
        application_id = _application_id_from_response(database, external_application_id, application_response)
        if application_id is None:
            raise RuntimeError("email application upsert returned no application ID")

        provider_event_id = message_id or f"accepted:{external_application_id}"
        (
            database.schema(SCHEMA)
            .table("email_delivery_events")
            .upsert(
                {
                    "application_id": application_id,
                    "candidate_id": mapped_candidate_id,
                    "provider": provider.strip() or PROVIDER,
                    "provider_event_id": provider_event_id,
                    "message_reference": message_id,
                    "event_type": "sent",
                    "occurred_at": sent_at_value,
                    "metadata": {
                        "external_application_id": external_application_id,
                        "delivery_channel": delivery_channel.strip() or "email",
                    },
                },
                on_conflict="provider,provider_event_id",
            )
            .execute()
        )
        return DeliverySyncResult("synced", application_id=application_id)
    except Exception as error:
        LOGGER.warning(
            "Supabase delivery sync failed for external application %s (%s)",
            external_application_id,
            type(error).__name__,
        )
        return DeliverySyncResult("failed", reason=type(error).__name__)

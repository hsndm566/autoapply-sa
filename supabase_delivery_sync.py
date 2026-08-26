"""Server-only synchronization of accepted email-delivery facts to Supabase.

This module is deliberately usable only by trusted backend code. It derives the
candidate from the active delivery-client mapping instead of trusting a browser
or portal caller, hashes recipient addresses before persistence, and never logs
credential values or recipient addresses.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import requests


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


@dataclass(frozen=True)
class _RestResponse:
    data: object


class _ServerPostgrestQuery:
    """Small server-only adapter for the REST calls used by delivery sync."""

    def __init__(self, client: "_ServerPostgrestClient", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.params: list[tuple[str, str]] = []
        self.operation = "select"
        self.payload: Mapping[str, Any] | None = None
        self.conflict_target: str | None = None

    def select(self, columns: str) -> "_ServerPostgrestQuery":
        self.params.append(("select", columns))
        return self

    def eq(self, name: str, value: object) -> "_ServerPostgrestQuery":
        normalized = str(value).lower() if isinstance(value, bool) else str(value)
        self.params.append((name, f"eq.{normalized}"))
        return self

    def limit(self, count: int) -> "_ServerPostgrestQuery":
        self.params.append(("limit", str(count)))
        return self

    def upsert(self, payload: Mapping[str, Any], *, on_conflict: str) -> "_ServerPostgrestQuery":
        self.operation = "upsert"
        self.payload = payload
        self.conflict_target = on_conflict
        return self

    def execute(self) -> _RestResponse:
        endpoint = f"{self.client.base_url}/{self.table_name}"
        if self.operation == "select":
            response = requests.get(endpoint, headers=self.client.headers, params=self.params, timeout=20)
        else:
            if self.payload is None or self.conflict_target is None:
                raise RuntimeError("delivery-sync upsert request is incomplete")
            response = requests.post(
                endpoint,
                headers={**self.client.headers, "Prefer": "resolution=merge-duplicates,return=representation"},
                params={"on_conflict": self.conflict_target},
                json=dict(self.payload),
                timeout=20,
            )
        response.raise_for_status()
        return _RestResponse(response.json())


class _ServerPostgrestClient:
    """Server-only REST client that avoids initializing Auth or Realtime clients."""

    def __init__(self, project_url: str, secret_key: str, schema: str = "public") -> None:
        self.base_url = f"{project_url.rstrip('/')}/rest/v1"
        self.secret_key = secret_key
        self.schema_name = schema

    @property
    def headers(self) -> dict[str, str]:
        # Modern Supabase secret keys must be sent as apikey values, not bearer JWTs.
        return {
            "apikey": self.secret_key,
            "Accept-Profile": self.schema_name,
            "Content-Profile": self.schema_name,
        }

    def schema(self, schema_name: str) -> "_ServerPostgrestClient":
        return _ServerPostgrestClient(self.base_url.removesuffix("/rest/v1"), self.secret_key, schema_name)

    def table(self, table_name: str) -> _ServerPostgrestQuery:
        return _ServerPostgrestQuery(self, table_name)


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
        return _ServerPostgrestClient(url, service_role_key)
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


async def sync_accepted_application(
    *,
    external_application_id: str,
    external_client_id: int,
    sender_email: str,
    recipient_email: str,
    company: str,
    role: str,
    city: str | None,
    provider_message_id: str | None,
    sent_at: datetime | str,
) -> dict[str, object]:
    """Synchronize one accepted email without blocking the scheduled sender.

    The sync implementation is isolated in a worker thread because the official
    Supabase Python client is synchronous. This public async contract lets the
    sender await the database result while preserving an entirely server-side
    credential boundary.
    """
    result = await asyncio.to_thread(
        sync_accepted_delivery,
        candidate_id=None,
        external_application_id=external_application_id,
        external_client_id=external_client_id,
        sender_email=sender_email,
        recipient_email=recipient_email,
        company=company,
        role=role,
        city=city,
        delivery_channel="email",
        provider_message_id=provider_message_id,
        send_status="accepted",
        sent_at=sent_at,
        provider=PROVIDER,
    )
    if result.status == "synced":
        return {"synced": True, "application_id": result.application_id}
    if result.status == "skipped_mapping_missing":
        return {"skipped": True, "reason": "no_mapping"}
    if result.status.startswith("skipped_"):
        return {"skipped": True, "reason": result.reason or result.status.removeprefix("skipped_")}
    return {"synced": False, "reason": result.reason or result.status}

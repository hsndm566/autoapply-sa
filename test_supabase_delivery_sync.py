"""Offline tests for the server-only accepted-delivery Supabase sync helper."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import supabase_delivery_sync as sync


class FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.operation = "select"
        self.payload: dict[str, Any] | None = None
        self.conflict_target: str | None = None

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, name: str, value: Any) -> "FakeQuery":
        self.filters.append((name, value))
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def upsert(self, payload: dict[str, Any], *, on_conflict: str) -> "FakeQuery":
        self.operation = "upsert"
        self.payload = payload
        self.conflict_target = on_conflict
        return self

    def execute(self) -> FakeResponse:
        if self.operation == "upsert":
            assert self.payload is not None
            self.database.upserts.append((self.table_name, self.payload, self.conflict_target))
            if self.table_name == "email_applications":
                return FakeResponse([{"id": self.database.application_id}])
            return FakeResponse([])
        if self.table_name == "delivery_client_mappings":
            return FakeResponse([{"candidate_id": self.database.candidate_id}] if self.database.mapping_exists else [])
        if self.table_name == "email_applications":
            return FakeResponse([{"id": self.database.application_id}])
        return FakeResponse([])


class FakeSupabase:
    def __init__(self, *, mapping_exists: bool = True) -> None:
        self.candidate_id = "11111111-1111-1111-1111-111111111111"
        self.application_id = "22222222-2222-2222-2222-222222222222"
        self.mapping_exists = mapping_exists
        self.upserts: list[tuple[str, dict[str, Any], str | None]] = []

    def schema(self, schema_name: str) -> "FakeSupabase":
        self.schema_name = schema_name
        return self

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)


class SupabaseDeliverySyncTests(unittest.TestCase):
    def test_server_client_uses_api_key_header_for_modern_secret(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SUPABASE_DEV_URL": "https://dev.example.test/",
                "SUPABASE_DEV_SERVICE_ROLE_KEY": "sb_secret_test",
            },
            clear=False,
        ):
            client = sync._server_client()

        self.assertIsInstance(client, sync._ServerPostgrestClient)
        assert client is not None
        self.assertEqual("https://dev.example.test/rest/v1", client.base_url)
        self.assertEqual(
            {
                "apikey": "sb_secret_test",
                "Accept-Profile": "public",
                "Content-Profile": "public",
            },
            client.headers,
        )

    def test_hash_recipient_email_normalizes_before_hashing(self) -> None:
        self.assertEqual(sync.hash_recipient_email("person@example.test"), sync.hash_recipient_email(" Person@Example.Test "))

    def test_sync_upserts_application_and_idempotent_sent_event(self) -> None:
        database = FakeSupabase()
        result = sync.sync_accepted_delivery(
            candidate_id=None,
            external_application_id="scheduled-application-1",
            external_client_id=2,
            sender_email="apply1@hsndm.tech",
            recipient_email="recipient@example.test",
            company="Example Company",
            role="Industrial Engineer",
            city="Jeddah",
            delivery_channel="email",
            provider_message_id="brevo-message-1",
            send_status="accepted",
            sent_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            client=database,
        )

        self.assertTrue(result.synced)
        self.assertEqual(database.application_id, result.application_id)
        self.assertEqual(["email_applications", "email_delivery_events"], [entry[0] for entry in database.upserts])
        application_payload = database.upserts[0][1]
        self.assertEqual(database.candidate_id, application_payload["candidate_id"])
        self.assertNotIn("recipient_email", application_payload)
        self.assertEqual(sync.hash_recipient_email("recipient@example.test"), application_payload["recipient_email_hash"])
        event_payload = database.upserts[1][1]
        self.assertEqual(database.application_id, event_payload["application_id"])
        self.assertEqual("brevo-message-1", event_payload["provider_event_id"])
        self.assertEqual("provider,provider_event_id", database.upserts[1][2])

    def test_sync_skips_when_no_active_mapping_exists(self) -> None:
        database = FakeSupabase(mapping_exists=False)
        result = sync.sync_accepted_delivery(
            candidate_id=None,
            external_application_id="scheduled-application-2",
            external_client_id=3,
            sender_email="apply2@hsndm.tech",
            recipient_email="recipient@example.test",
            company="Example Company",
            role="Customer Service Representative",
            city="Jeddah",
            delivery_channel="email",
            provider_message_id=None,
            send_status="accepted",
            sent_at="2026-08-26T00:00:00+00:00",
            client=database,
        )

        self.assertEqual("skipped_mapping_missing", result.status)
        self.assertEqual([], database.upserts)

    def test_sync_rejects_non_accepted_status_without_database_write(self) -> None:
        database = FakeSupabase()
        result = sync.sync_accepted_delivery(
            candidate_id=None,
            external_application_id="scheduled-application-3",
            external_client_id=2,
            sender_email="apply1@hsndm.tech",
            recipient_email="recipient@example.test",
            company="Example Company",
            role="Industrial Engineer",
            city="Jeddah",
            delivery_channel="email",
            provider_message_id=None,
            send_status="uncertain",
            sent_at="2026-08-26T00:00:00+00:00",
            client=database,
        )

        self.assertEqual("skipped_non_accepted", result.status)
        self.assertEqual([], database.upserts)

    def test_async_api_returns_requested_no_mapping_summary(self) -> None:
        database = FakeSupabase(mapping_exists=False)
        original_server_client = sync._server_client
        sync._server_client = lambda: database
        try:
            result = asyncio.run(sync.sync_accepted_application(
                external_application_id="scheduled-application-4",
                external_client_id=3,
                sender_email="apply2@hsndm.tech",
                recipient_email="recipient@example.test",
                company="Example Company",
                role="Customer Service Representative",
                city="Jeddah",
                provider_message_id=None,
                sent_at="2026-08-26T00:00:00+00:00",
            ))
        finally:
            sync._server_client = original_server_client

        self.assertEqual({"skipped": True, "reason": "no_mapping"}, result)
        self.assertEqual([], database.upserts)


if __name__ == "__main__":
    unittest.main(verbosity=2)

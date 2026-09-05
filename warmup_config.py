"""Retired legacy warm-up bounds retained only for offline compatibility tests.

No real client identity belongs in source control. Production campaign identity is
loaded from the private campaign datastore and review context.
"""
from __future__ import annotations

WARMUP_SCOPE = "retired-verified-contact-fixture"
WARMUP_ENVIRONMENT_FLAG = "AUTOAPPLY_ONE_TIME_WARMUP"
SCHEDULED_DELIVERY_SCOPE = "retired-scheduled-delivery-fixture"
SCHEDULED_DELIVERY_ENVIRONMENT_FLAG = "AUTOAPPLY_SCHEDULED_DELIVERY"
WARMUP_EVIDENCE_TYPE = "verified_contact"
WARMUP_CLIENTS = {
    2: {"sender_email": "client2@example.test", "client_name": "Sample Candidate Two"},
    3: {"sender_email": "client3@example.test", "client_name": "Sample Candidate Three"},
}


def is_authorized_warmup_sender(client_id: int, sender_email: str) -> bool:
    expected = WARMUP_CLIENTS.get(int(client_id), {}).get("sender_email", "")
    return bool(expected and expected.casefold() == str(sender_email).strip().casefold())

"""Immutable bounds for the user-authorized August 2026 verified-contact warm-up."""
from __future__ import annotations

WARMUP_SCOPE = "verified-contact-clients-2-3-2026-08-20"
WARMUP_ENVIRONMENT_FLAG = "AUTOAPPLY_ONE_TIME_WARMUP"
WARMUP_EVIDENCE_TYPE = "verified_contact"
WARMUP_CLIENTS = {
    2: {"sender_email": "apply1@hsndm.tech", "client_name": "Saif Ahmed Al Nimr"},
    3: {"sender_email": "apply2@hsndm.tech", "client_name": "Amro Alkabeer"},
}


def is_authorized_warmup_sender(client_id: int, sender_email: str) -> bool:
    expected = WARMUP_CLIENTS.get(int(client_id), {}).get("sender_email", "")
    return bool(expected and expected.casefold() == str(sender_email).strip().casefold())

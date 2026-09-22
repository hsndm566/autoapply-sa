"""Authorization bounds for verified-contact application delivery.

Sender addresses are reusable delivery identities. They are deliberately not
bound to a person or client ID. Candidate identity is supplied by the current
client/application package and rechecked by the Auditor before delivery.
"""
from __future__ import annotations

WARMUP_SCOPE = "verified-contact-one-time"
WARMUP_ENVIRONMENT_FLAG = "AUTOAPPLY_ONE_TIME_WARMUP"
SCHEDULED_DELIVERY_SCOPE = "verified-contact-scheduled"
SCHEDULED_DELIVERY_ENVIRONMENT_FLAG = "AUTOAPPLY_SCHEDULED_DELIVERY"
WARMUP_EVIDENCE_TYPE = "verified_contact"

AUTHORIZED_BREVO_SENDERS = frozenset({
    "apply@hsndm.tech",
    "apply1@hsndm.tech",
    "apply2@hsndm.tech",
})


def is_authorized_sender(sender_email: str) -> bool:
    return str(sender_email or "").strip().casefold() in AUTHORIZED_BREVO_SENDERS


def is_authorized_warmup_sender(_client_id: int, sender_email: str) -> bool:
    """Backward-compatible wrapper; authorization is sender-based, never client-ID-based."""
    return is_authorized_sender(sender_email)

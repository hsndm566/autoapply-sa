#!/usr/bin/env python3
"""Backfill real Brevo delivery events into the service-role-only Supabase audit.

No email is sent by this script. Only events linked to an accepted secure batch,
matching both the provider message ID and recipient, may be persisted.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import urllib.parse
import urllib.request

SAFE_SENDERS = {"Yasmin Adam": "apply@hsndm.tech", "Sultan Saud": "apply1@hsndm.tech"}
EVENT_NAMES = {
    "requests": "request", "request": "request", "sent": "sent",
    "delivered": "delivered", "deferred": "deferred",
    "hardbounces": "hardBounce", "hardbounce": "hardBounce", "hard_bounce": "hardBounce",
    "blocked": "blocked", "invalid": "invalid",
    "spam": "spam", "spamreport": "spam", "complaint": "spam",
}
EVENT_PRIORITY = {"request": 0, "sent": 1, "deferred": 2, "delivered": 3,
                  "blocked": 4, "hardBounce": 5, "invalid": 6, "spam": 7}


def get_json(url, headers, method="GET", payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.loads(response.read() or b"null")


def pages(url, headers, list_key=None, page_size=1000, max_pages=100):
    """Fail closed on unexpectedly incomplete API pagination."""
    offset = 0
    for _ in range(max_pages):
        params = urllib.parse.urlencode({"limit": page_size, "offset": offset})
        result = get_json(url + ("&" if "?" in url else "?") + params, headers)
        page = result.get(list_key) if list_key else result
        if not isinstance(page, list):
            raise RuntimeError("Provider or database pagination returned an invalid result")
        yield from page
        if len(page) < page_size:
            return
        offset += len(page)
    raise RuntimeError("Refusing incomplete pagination at safety cap")


def event_timestamp(event):
    raw = event.get("ts_epoch")
    if raw is not None:
        try:
            return datetime.fromtimestamp(float(raw), timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            pass
    date = event.get("date")
    if date:
        try:
            parsed = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return None


def plan_event_writes(provider_events, ledger):
    """Keep actual provider evidence, including precedence of a hard bounce."""
    groups = defaultdict(list)
    stats = Counter()
    for event in provider_events:
        mid = str(event.get("messageId") or event.get("message-id") or "").strip()
        email = str(event.get("email") or "").strip().lower()
        if not mid or mid not in ledger:
            continue
        if email != ledger[mid]:
            stats["recipient_mismatch"] += 1
            continue
        raw_type = str(event.get("event") or "").lower().strip()
        if raw_type in {"softbounces", "softbounce", "soft_bounce"}:
            stats["soft_bounces_for_manual_review"] += 1
            continue  # Never convert a transient soft bounce into permanent suppression.
        target_type = EVENT_NAMES.get(raw_type)
        if not target_type:
            stats["other_event_types"] += 1
            continue
        when = event_timestamp(event)
        if not when:
            raise RuntimeError("Provider event for known message has no valid timestamp")
        event_key = [
            mid, email, raw_type, str(event.get("ts_epoch") or event.get("date") or ""),
            str(event.get("reason") or event.get("message") or ""),
            str(event.get("id") or ""),
        ]
        eid = "brevo:" + hashlib.sha256(json.dumps(event_key, ensure_ascii=False).encode()).hexdigest()
        groups[mid].append({
            "p_event_id": eid, "p_provider_message_id": mid,
            "p_recipient_email": email, "p_event_type": target_type, "p_event_at": when,
        })
    writes = []
    for mid, entries in groups.items():
        kinds = {e["p_event_type"] for e in entries}
        if "hardBounce" in kinds or "invalid" in kinds or "spam" in kinds:
            # Keep evidence of conflicts, but never allow a delivered event to
            # override a hard-bounce or complaint in the application status.
            stats["bounce_or_complaint_message_ids"] += 1
            entries = [e for e in entries if e["p_event_type"] != "delivered"]
        deduped = {e["p_event_id"]: e for e in entries}
        writes.extend(sorted(deduped.values(), key=lambda e: (EVENT_PRIORITY[e["p_event_type"]], e["p_event_at"])))
    writes.sort(key=lambda e: (e["p_provider_message_id"], EVENT_PRIORITY[e["p_event_type"]], e["p_event_at"]))
    stats["approved_event_writes"] = len(writes)
    return writes, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write only authenticated matched events via the service-role RPC")
    args = parser.parse_args()
    supabase = os.environ["SUPABASE_URL"].rstrip("/")
    secret = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    db_headers = {"apikey": secret, "Authorization": "Bearer " + secret, "Content-Type": "application/json"}
    key = get_json(supabase + "/rest/v1/rpc/get_secure_outbound_brevo_key", db_headers, "POST", {})
    if not isinstance(key, str) or not key.strip():
        raise RuntimeError("Brevo secure credential unavailable")
    provider_headers = {"api-key": key.strip(), "accept": "application/json"}

    # Read the secure ledger before accepting any provider event: the matching
    # key is the exact ID Brevo returned to the secure sender, not a fuzzy address.
    ledger = {}
    q = urllib.parse.urlencode({
        "select": "candidate_name,sender_email,state,result",
        "state": "in.(sent,failed,sending)",
    })
    for batch in pages(supabase + "/rest/v1/secure_outbound_batches?" + q, db_headers):
        candidate = batch.get("candidate_name")
        if batch.get("sender_email") != SAFE_SENDERS.get(candidate):
            continue
        for item in (batch.get("result") or {}).get("messages") or []:
            mid = str(item.get("messageId") or "").strip()
            addr = str(item.get("to") or "").lower().strip()
            if mid and "@" in addr:
                if mid in ledger and ledger[mid] != addr:
                    raise RuntimeError("Conflicting provider message IDs in secure ledger")
                ledger[mid] = addr
    if not ledger:
        raise RuntimeError("No securely accepted messages found: cannot reconcile")

    start = max(datetime(2026, 10, 5, tzinfo=timezone.utc).date(),
                (datetime.now(timezone.utc) - timedelta(days=29)).date())
    end = datetime.now(timezone.utc).date()
    event_url = "https://api.brevo.com/v3/smtp/statistics/events?" + urllib.parse.urlencode({
        "startDate": start.isoformat(), "endDate": end.isoformat(), "sort": "asc",
    })
    events = list(pages(event_url, provider_headers, list_key="events", page_size=5000, max_pages=20))
    writes, stats = plan_event_writes(events, ledger)
    if args.apply:
        for item in writes:
            reply = get_json(supabase + "/rest/v1/rpc/apply_brevo_delivery_event",
                             db_headers, "POST", item)
            if not isinstance(reply, dict) or not reply.get("ok"):
                raise RuntimeError("Delivery-event RPC did not confirm a write")
            stats["already_seen" if reply.get("duplicate") else "newly_persisted"] += 1

    # No API keys, CVs, message content, personal data or provider event payloads in output.
    print(json.dumps({
        "mode": "apply" if args.apply else "dry_run",
        "tracked_provider_ids": len(ledger),
        "provider_events_seen": len(events),
        "event_window": [start.isoformat(), end.isoformat()],
        "counts": dict(stats),
    }, sort_keys=True))


if __name__ == "__main__":
    main()

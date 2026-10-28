"""Sync Ready + verified Notion contacts into the scheduled-delivery jobs file.

Fail closed: only Status=Ready, Purpose=Job application/Both, and an approved
Verification value are eligible. Existing jobs are preserved. Tracking.csv is
used to avoid re-queuing recipients already sent.
"""
from __future__ import annotations
import csv, json, os
from pathlib import Path
import requests

APPROVED_VERIFICATIONS = {"Official source", "Historical verified", "DNS verified"}
APPROVED_PURPOSES = {"Job application", "Both"}
EXCLUDED_STATUSES = {"Sent", "Bounced", "Do not send", "Needs verification"}

def _headers():
    token = os.environ.get("NOTION_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("NOTION_API_TOKEN is required")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

def fetch_ready_contacts(database_id: str):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    payload = {"page_size": 100}
    rows = []
    while True:
        response = requests.post(url, headers=_headers(), json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        rows.extend(body.get("results", []))
        if not body.get("has_more"):
            return rows
        payload["start_cursor"] = body["next_cursor"]

def prop_text(prop):
    typ = prop.get("type")
    if typ == "title":
        return "".join(x.get("plain_text", "") for x in prop.get("title", [])).strip()
    if typ == "rich_text":
        return "".join(x.get("plain_text", "") for x in prop.get("rich_text", [])).strip()
    if typ == "email":
        return (prop.get("email") or "").strip()
    if typ == "select":
        return ((prop.get("select") or {}).get("name") or "").strip()
    return ""

def main():
    database_id = os.environ.get("NOTION_CONTACTS_DATABASE_ID", "").strip()
    if not database_id:
        raise RuntimeError("NOTION_CONTACTS_DATABASE_ID is required")

    jobs_path = Path("jobs.csv")
    tracking_path = Path("tracking.csv")
    with jobs_path.open(newline="", encoding="utf-8") as f:
        existing = list(csv.DictReader(f))
        fields = list(existing[0].keys()) if existing else [
            "recipient_email","company","role","city","client_id","evidence_type","public_job_url"
        ]

    tracked = set()
    if tracking_path.exists():
        with tracking_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                email = (row.get("recipient_email") or "").strip().casefold()
                if email:
                    tracked.add(email)
    known = {(r.get("recipient_email") or "").strip().casefold() for r in existing}

    added = 0
    excluded = {}
    next_client = 2
    for page in fetch_ready_contacts(database_id):
        p = page.get("properties", {})
        status = prop_text(p.get("Status", {}))
        verification = prop_text(p.get("Verification", {}))
        purpose = prop_text(p.get("Purpose", {}))
        email = prop_text(p.get("Email", {})).casefold()
        company = prop_text(p.get("Company", {}))
        role = prop_text(p.get("Target Role", {})) or "Industrial Engineering / Operations Role"

        reason = None
        if status != "Ready":
            reason = f"status:{status or 'blank'}"
        elif status in EXCLUDED_STATUSES:
            reason = f"status:{status}"
        elif verification not in APPROVED_VERIFICATIONS:
            reason = f"verification:{verification or 'blank'}"
        elif purpose not in APPROVED_PURPOSES:
            reason = f"purpose:{purpose or 'blank'}"
        elif not email or "@" not in email:
            reason = "invalid_email"
        elif email in tracked:
            reason = "already_tracked"
        elif email in known:
            reason = "already_queued"

        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue

        existing.append({
            "recipient_email": email,
            "company": company or email.split("@",1)[1],
            "role": role,
            "city": "",
            "client_id": str(next_client),
            "evidence_type": "verified_contact",
            "public_job_url": "",
        })
        next_client = 3 if next_client == 2 else 2
        known.add(email)
        added += 1

    with jobs_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing)

    print(json.dumps({"notion_sync": {"added": added, "excluded": excluded}}, sort_keys=True))

if __name__ == "__main__":
    main()

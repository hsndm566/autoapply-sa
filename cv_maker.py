"""Durable CV-maker and manual-transfer order flow for AutoApply SA."""
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

LOG = logging.getLogger("autoapply.cv_maker")
LOCK = threading.Lock()
DB_PATH = Path(os.environ.get("CV_MAKER_DB_PATH", os.path.join(os.environ.get("CV_STORAGE_DIR", "data/cv"), "cv-maker.db")))
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MAX_TEXT = int(os.environ.get("CV_MAKER_MAX_TEXT", "30000"))
ORDER_RETENTION_DAYS = int(os.environ.get("CV_ORDER_RETENTION_DAYS", "30"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: object, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with LOCK, _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cv_drafts (
              id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
              source_sha256 TEXT NOT NULL, target_role TEXT NOT NULL, job_description TEXT NOT NULL,
              result_json TEXT NOT NULL, model TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cv_orders (
              id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              customer_name TEXT NOT NULL, customer_email TEXT NOT NULL, price_sar INTEGER NOT NULL,
              status TEXT NOT NULL, payer_name TEXT NOT NULL DEFAULT '', transfer_reference TEXT NOT NULL DEFAULT '',
              reviewed_at TEXT NOT NULL DEFAULT '', reviewer_note TEXT NOT NULL DEFAULT '',
              FOREIGN KEY(draft_id) REFERENCES cv_drafts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cv_orders_status ON cv_orders(status, updated_at DESC);
            """
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(days=ORDER_RETENTION_DAYS)).isoformat()
        conn.execute("DELETE FROM cv_drafts WHERE expires_at < ?", (cutoff,))
        conn.commit()


def bank_details() -> dict[str, object]:
    name = clean(os.environ.get("BANK_NAME"), 120)
    account = clean(os.environ.get("BANK_ACCOUNT_NAME"), 160)
    iban = clean(os.environ.get("BANK_IBAN"), 80)
    account_number = clean(os.environ.get("BANK_ACCOUNT_NUMBER"), 40)
    swift = clean(os.environ.get("BANK_SWIFT_CODE"), 40)
    configured = bool(name and account and iban.startswith("SA") and len(iban) == 24 and account_number.isdigit() and 10 <= len(account_number) <= 24 and 8 <= len(swift) <= 11)
    return {
        "configured": configured,
        "bank_name": name,
        "account_name": account,
        "iban": iban,
        "account_number": account_number,
        "swift_code": swift,
        "amount_sar": int(os.environ.get("CV_PRICE_SAR", "29")),
        "reference_instruction": "Use your order ID as the transfer reference.",
    }


def health() -> dict[str, object]:
    provider = "deepseek" if os.environ.get("DEEPSEEK_API_KEY") else "unconfigured"
    db_ready = False
    try:
        initialize()
        db_ready = True
    except Exception as exc:  # health must not crash the backend
        LOG.error("CV maker database health failed: %s", type(exc).__name__)
    bank = bank_details()
    ready = bool(db_ready and bank["configured"] and provider != "unconfigured" and os.environ.get("ADMIN_API_TOKEN"))
    return {"ready": ready, "database_ready": db_ready, "bank_configured": bank["configured"], "admin_configured": bool(os.environ.get("ADMIN_API_TOKEN")), "model_provider": provider, "price_sar": bank["amount_sar"]}


def _schema_valid(payload: object) -> bool:
    if not isinstance(payload, dict) or not isinstance(payload.get("english"), dict) or not isinstance(payload.get("arabic"), dict):
        return False
    for version in (payload["english"], payload["arabic"]):
        if not isinstance(version.get("headline"), str) or not isinstance(version.get("summary"), str):
            return False
        for field in ("experience", "education", "skills", "certifications", "languages"):
            if not isinstance(version.get(field), list) or not all(isinstance(item, str) for item in version[field]):
                return False
    return isinstance(payload.get("ats_notes"), list)


def _prompt(source_text: str, target_role: str, job_description: str) -> str:
    return f"""Produce JSON only. You are an ATS CV editor. Use only facts in the source CV. Never invent employers, dates, degrees, certifications, numbers, contact details, or achievements. If facts are missing, omit them. Return exactly this JSON shape: {{\"english\":{{\"headline\":\"\",\"summary\":\"\",\"experience\":[],\"education\":[],\"skills\":[],\"certifications\":[],\"languages\":[]}},\"arabic\":{{\"headline\":\"\",\"summary\":\"\",\"experience\":[],\"education\":[],\"skills\":[],\"certifications\":[],\"languages\":[]}},\"ats_notes\":[]}}. Create concise, truthful English and Arabic ATS-ready versions. Tailor only with truthful keywords supported by the CV or job description.\n\nTarget role: {target_role or 'Broadly optimize for the candidate background'}\n\nJob description: {job_description or 'Not provided'}\n\nSource CV:\n{source_text}"""


def generate(source_text: str, target_role: str, job_description: str) -> tuple[str, dict[str, object]]:
    source_text = clean(source_text, MAX_TEXT)
    if len(source_text) < 80:
        raise ValueError("A readable CV text of at least 80 characters is required.")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("CV maker model is not configured.")
    body = {"model": os.environ.get("CV_MODEL", "deepseek-v4-flash"), "thinking": {"type": "disabled"}, "temperature": 0.2, "max_tokens": 3200, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": "Return valid JSON only."}, {"role": "user", "content": _prompt(source_text, clean(target_role, 180), clean(job_description, 5000))}]}
    response: requests.Response | None = None
    for attempt in range(3):
        try:
            response = requests.post(DEEPSEEK_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body, timeout=45)
            if response.status_code not in {429, 500, 502, 503, 504} or attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))
        except requests.RequestException:
            if attempt == 2:
                raise RuntimeError("CV maker model is unavailable.")
            time.sleep(0.5 * (attempt + 1))
    if response is None or not response.ok:
        raise RuntimeError("CV maker model is unavailable.")
    try:
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
    except Exception as exc:
        raise RuntimeError("CV maker returned an invalid result.") from exc
    if not _schema_valid(result):
        raise RuntimeError("CV maker returned an incomplete result.")
    draft_id = f"DRAFT-{uuid.uuid4().hex[:12].upper()}"
    created = datetime.now(timezone.utc)
    with LOCK, _connect() as conn:
        conn.execute("INSERT INTO cv_drafts (id,created_at,expires_at,source_sha256,target_role,job_description,result_json,model) VALUES (?,?,?,?,?,?,?,?)", (draft_id, created.isoformat(), (created + timedelta(days=ORDER_RETENTION_DAYS)).isoformat(), hashlib.sha256(source_text.encode("utf-8")).hexdigest(), clean(target_role, 180), clean(job_description, 5000), json.dumps(result, ensure_ascii=False), body["model"]))
        conn.commit()
    return draft_id, result


def create_order(draft_id: str, customer_name: str, customer_email: str) -> dict[str, object]:
    if not health()["database_ready"]:
        raise RuntimeError("Order storage is unavailable.")
    bank = bank_details()
    if not bank["configured"]:
        raise RuntimeError("Bank transfer configuration is incomplete.")
    if "@" not in customer_email:
        raise ValueError("A valid customer email is required.")
    with LOCK, _connect() as conn:
        draft = conn.execute("SELECT id FROM cv_drafts WHERE id=?", (draft_id,)).fetchone()
        if not draft:
            raise ValueError("The CV draft is no longer available. Generate it again.")
        order_id = f"CV-{uuid.uuid4().hex[:10].upper()}"
        timestamp = now()
        conn.execute("INSERT INTO cv_orders (id,draft_id,created_at,updated_at,customer_name,customer_email,price_sar,status) VALUES (?,?,?,?,?,?,?,?)", (order_id, draft_id, timestamp, timestamp, clean(customer_name, 120), clean(customer_email, 200), bank["amount_sar"], "pending_transfer"))
        conn.commit()
    return {"order": order(order_id), "bank": bank}


def order(order_id: str, include_draft: bool = False) -> dict[str, object] | None:
    with LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM cv_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["has_export"] = data["status"] == "approved"
        if include_draft:
            draft = conn.execute("SELECT result_json FROM cv_drafts WHERE id=?", (data["draft_id"],)).fetchone()
            data["result"] = json.loads(draft["result_json"]) if draft else None
        return data


def submit_transfer(order_id: str, payer_name: str, transfer_reference: str) -> dict[str, object]:
    if not transfer_reference:
        raise ValueError("Transfer reference is required.")
    with LOCK, _connect() as conn:
        row = conn.execute("SELECT status FROM cv_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise ValueError("Order not found.")
        if row["status"] != "pending_transfer":
            raise ValueError("Order is not awaiting transfer details.")
        conn.execute("UPDATE cv_orders SET status=?,payer_name=?,transfer_reference=?,updated_at=? WHERE id=?", ("transfer_submitted", clean(payer_name, 160), clean(transfer_reference, 160), now(), order_id))
        conn.commit()
    return order(order_id) or {}


def review_order(order_id: str, decision: str, note: str = "") -> dict[str, object]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Invalid review decision.")
    with LOCK, _connect() as conn:
        row = conn.execute("SELECT status FROM cv_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            raise ValueError("Order not found.")
        if decision == "approved" and row["status"] != "transfer_submitted":
            raise ValueError("Only submitted transfers can be approved.")
        conn.execute("UPDATE cv_orders SET status=?,reviewed_at=?,reviewer_note=?,updated_at=? WHERE id=?", (decision, now(), clean(note, 500), now(), order_id))
        conn.commit()
    return order(order_id) or {}


def list_orders(limit: int = 100) -> list[dict[str, object]]:
    with LOCK, _connect() as conn:
        rows = conn.execute("SELECT id,draft_id,created_at,updated_at,customer_name,customer_email,price_sar,status,payer_name,transfer_reference,reviewed_at,reviewer_note FROM cv_orders ORDER BY updated_at DESC LIMIT ?", (max(1, min(limit, 300)),)).fetchall()
    return [{**dict(row), "has_export": row["status"] == "approved"} for row in rows]


def export_html(order_id: str, language: str) -> str:
    item = order(order_id, include_draft=True)
    if not item:
        raise ValueError("Order not found.")
    if item["status"] != "approved":
        raise PermissionError("Payment has not been approved.")
    version = (item.get("result") or {}).get("arabic" if language == "ar" else "english")
    if not isinstance(version, dict):
        raise RuntimeError("Export is unavailable.")
    direction = "rtl" if language == "ar" else "ltr"
    title = html.escape(clean(version.get("headline"), 300))
    sections = [("الملخص المهني" if language == "ar" else "Professional Summary", [clean(version.get("summary"), 2000)]), ("الخبرة المهنية" if language == "ar" else "Experience", version.get("experience", [])), ("التعليم" if language == "ar" else "Education", version.get("education", [])), ("المهارات" if language == "ar" else "Skills", version.get("skills", [])), ("الشهادات" if language == "ar" else "Certifications", version.get("certifications", [])), ("اللغات" if language == "ar" else "Languages", version.get("languages", []))]
    body = "".join(f"<section><h2>{html.escape(label)}</h2><ul>{''.join(f'<li>{html.escape(clean(item, 1500))}</li>' for item in values if clean(item, 1500))}</ul></section>" for label, values in sections if values)
    return f"<!doctype html><html lang='{language}' dir='{direction}'><head><meta charset='utf-8'><title>{title}</title><style>body{{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;color:#111;line-height:1.45}}h1{{font-size:28px;border-bottom:2px solid #111;padding-bottom:10px}}h2{{font-size:15px;border-bottom:1px solid #aaa;padding-bottom:4px;margin-top:22px}}li{{margin:4px 0}}@media print{{body{{margin:18mm}}}}</style></head><body><h1>{title}</h1>{body}</body></html>"

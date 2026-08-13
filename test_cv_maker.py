from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="cv-maker-test-"))
os.environ["CV_MAKER_DB_PATH"] = str(root / "cv-maker.db")
os.environ["BANK_NAME"] = "Test Bank"
os.environ["BANK_ACCOUNT_NAME"] = "Test Account"
os.environ["BANK_IBAN"] = "SA0000000000000000000000"
os.environ["BANK_ACCOUNT_NUMBER"] = "1234567890"
os.environ["BANK_SWIFT_CODE"] = "TESTSAJE"
os.environ["CV_PRICE_SAR"] = "29"
os.environ["ADMIN_API_TOKEN"] = "test-admin"
os.environ["DEEPSEEK_API_KEY"] = "test-key"

import cv_maker  # noqa: E402

sample = {
    "english": {"headline": "Test CV", "summary": "Summary", "experience": ["Experience"], "education": ["Education"], "skills": ["Skill"], "certifications": [], "languages": ["English"]},
    "arabic": {"headline": "سيرة اختبار", "summary": "ملخص", "experience": ["خبرة"], "education": ["تعليم"], "skills": ["مهارة"], "certifications": [], "languages": ["العربية"]},
    "ats_notes": [],
}

cv_maker.initialize()
with cv_maker._connect() as conn:  # noqa: SLF001 - test fixture setup
    conn.execute("INSERT INTO cv_drafts (id,created_at,expires_at,source_sha256,target_role,job_description,result_json,model) VALUES (?,?,?,?,?,?,?,?)", ("DRAFT-TEST", "2026-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00", "hash", "role", "", json.dumps(sample), "test"))
    conn.commit()

assert cv_maker.health()["ready"] is True
created = cv_maker.create_order("DRAFT-TEST", "Test Customer", "test@example.com")
order_id = created["order"]["id"]
assert cv_maker.order(order_id)["status"] == "pending_transfer"
try:
    cv_maker.review_order(order_id, "approved")
    raise AssertionError("Approval should require transfer submission")
except ValueError:
    pass
cv_maker.submit_transfer(order_id, "Test Customer", "CV-TEST")
assert cv_maker.order(order_id)["status"] == "transfer_submitted"
cv_maker.review_order(order_id, "approved")
assert cv_maker.order(order_id)["status"] == "approved"
document = cv_maker.export_html(order_id, "en")
assert "Test CV" in document
assert "no-store" not in document
print("CV_MAKER_TEST=PASS")

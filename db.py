#!/usr/bin/env python3
"""
db.py — Durable state for unattended operation.
SQLite (Railway free tier). Swap to Postgres later via DB_URL env (one line).
Stores: applications state machine, dead-letter, run flags (kill switch), budgets.
"""
import os, sqlite3, hashlib, json, time

DB_PATH = os.environ.get("DB_PATH", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "autoapply.db"))
SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    job_posting_hash TEXT NOT NULL UNIQUE,
    company TEXT,
    role TEXT,
    status TEXT NOT NULL DEFAULT 'scraped',
    attempt_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at REAL DEFAULT (strftime('%s','now')),
    updated_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT,
    job_posting_hash TEXT,
    stage TEXT,
    error TEXT,
    created_at REAL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS run_flags (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS run_budget (
    action_type TEXT PRIMARY KEY,
    max_per_hour INTEGER DEFAULT 20,
    max_per_run INTEGER DEFAULT 50
);
CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_client ON applications(client_id);
"""

def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("PRAGMA journal_mode=WAL;")
    c.executescript(SCHEMA)
    return c

def posting_hash(company, role, url=""):
    return hashlib.sha256(f"{company}|{role}|{url}".encode()).hexdigest()

def kill_switch_on():
    c = conn()
    row = c.execute("SELECT value FROM run_flags WHERE key='RUN_ENABLED'").fetchone()
    c.close()
    return row is not None and row[0] == "false"

def set_kill_switch(on):
    c = conn()
    c.execute("INSERT OR REPLACE INTO run_flags(key,value) VALUES('RUN_ENABLED',?)",
              ("false" if on else "true",))
    c.commit(); c.close()

def ingest_job(client_id, company, role, url=""):
    """Dedup at DB layer. Returns (hash, is_new). ON CONFLICT DO NOTHING."""
    h = posting_hash(company, role, url)
    c = conn()
    try:
        c.execute("INSERT INTO applications(client_id,job_posting_hash,company,role,status) VALUES(?,?,?,?,?)",
                  (client_id, h, company, role, "scraped"))
        c.commit()
        res = (h, True)
    except sqlite3.IntegrityError:
        res = (h, False)  # duplicate — already tracked
    c.close()
    return res

def set_status(h, status, error=None):
    c = conn()
    c.execute("UPDATE applications SET status=?,last_error=?,attempt_count=attempt_count+1,updated_at=strftime('%s','now') WHERE job_posting_hash=?",
              (status, error, h))
    c.commit(); c.close()

def dead_letter(client_id, h, stage, error):
    c = conn()
    c.execute("INSERT INTO dead_letter(client_id,job_posting_hash,stage,error) VALUES(?,?,?,?)",
              (client_id, h, stage, str(error)[:500]))
    c.commit(); c.close()

def metrics():
    c = conn()
    q = c.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall()
    dl = c.execute("SELECT COUNT(*) FROM dead_letter").fetchone()[0]
    last = c.execute("SELECT MAX(updated_at) FROM applications WHERE status='submitted'").fetchone()[0]
    c.close()
    by_status = {k: v for k, v in q}
    total = sum(by_status.values())
    success = by_status.get("submitted", 0)
    rate = round(100.0 * success / total, 1) if total else 0.0
    return {
        "total": total, "by_status": by_status,
        "dead_letter": dl, "success_rate_pct": rate,
        "last_submit_ts": last,
    }

def action_count_window(action_type, window_secs=3600):
    """How many actions of this type in the last window (for caps)."""
    c = conn()
    n = c.execute("SELECT COUNT(*) FROM applications WHERE status IN ('submitted','queued_submit') AND updated_at > strftime('%s','now')-?",
                  (window_secs,)).fetchone()[0]
    c.close()
    return n

def action_count_run(action_type):
    c = conn()
    n = c.execute("SELECT COUNT(*) FROM applications WHERE status IN ('submitted','queued_submit')").fetchone()[0]
    c.close()
    return n

def budget_for(action_type):
    c = conn()
    row = c.execute("SELECT max_per_hour, max_per_run FROM run_budget WHERE action_type=?", (action_type,)).fetchone()
    c.close()
    if not row:
        return (20, 50)
    return (row[0], row[1])

if __name__ == "__main__":
    print("DB init OK at", DB_PATH)
    print("metrics:", metrics())

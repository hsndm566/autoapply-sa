"""One-time migration helper for seeding the Heroku durable snapshot.

This module is inert unless called explicitly by the admin-gated migration endpoint.
It never returns CV contents or database rows.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import heroku_persistence

MAX_CV_BYTES = int(os.environ.get("MAX_CV_UPLOAD_BYTES", str(5 * 1024 * 1024)))


def _ensure_cv_blob_column(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(campaigns)").fetchall()}
    if "cv_blob" not in columns:
        connection.execute("ALTER TABLE campaigns ADD COLUMN cv_blob BLOB")


def _embed_existing_cvs(connection: sqlite3.Connection) -> int:
    embedded = 0
    rows = connection.execute(
        "SELECT id,cv_path FROM campaigns WHERE cv_path IS NOT NULL AND cv_path != '' AND cv_blob IS NULL"
    ).fetchall()
    for campaign_id, cv_path in rows:
        path = Path(str(cv_path)).expanduser()
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size <= 0 or size > MAX_CV_BYTES:
            continue
        payload = path.read_bytes()
        if not payload or len(payload) > MAX_CV_BYTES:
            continue
        connection.execute(
            "UPDATE campaigns SET cv_blob=?,updated_at=strftime('%s','now') WHERE id=?",
            (payload, campaign_id),
        )
        embedded += 1
    return embedded


def seed_snapshot(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if not heroku_persistence.configured():
        raise RuntimeError("remote snapshot storage is not configured")

    connection = sqlite3.connect(str(path), timeout=20)
    try:
        _ensure_cv_blob_column(connection)
        embedded = _embed_existing_cvs(connection)
        connection.commit()
    finally:
        connection.close()

    uploaded = heroku_persistence.snapshot(path, force=True)
    return {
        "ok": bool(uploaded),
        "snapshot_uploaded": bool(uploaded),
        "embedded_cv_count": embedded,
        "database_bytes": path.stat().st_size,
    }

"""Heroku portability wrapper for AutoApply SA.

This file intentionally leaves the production service and db modules unchanged.
It restores the durable SQLite snapshot before boot, keeps campaign CVs inside
SQLite, and snapshots writes to S3 Hero Dev.
"""
from __future__ import annotations

import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import db
import heroku_persistence
import service

MAX_CV_BYTES = int(os.environ.get("MAX_CV_UPLOAD_BYTES", str(5 * 1024 * 1024)))
SNAPSHOT_INTERVAL_SECONDS = max(1, int(os.environ.get("AUTOAPPLY_SNAPSHOT_INTERVAL_SECONDS", "3")))


def ensure_cv_blob_column() -> None:
    with db.connection() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(campaigns)").fetchall()}
        if "cv_blob" not in columns:
            connection.execute("ALTER TABLE campaigns ADD COLUMN cv_blob BLOB")


def embed_existing_cvs() -> int:
    embedded = 0
    with db.connection() as connection:
        rows = connection.execute(
            "SELECT id,cv_path FROM campaigns WHERE cv_path IS NOT NULL AND cv_path != '' AND cv_blob IS NULL"
        ).fetchall()
        for row in rows:
            path = Path(str(row["cv_path"])).expanduser()
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
                (payload, row["id"]),
            )
            embedded += 1
    return embedded


def materialize_cvs() -> int:
    target_dir = Path(service.CV_STORAGE_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    with db.connection() as connection:
        rows = connection.execute(
            "SELECT id,cv_path,cv_original_name,cv_blob FROM campaigns WHERE cv_blob IS NOT NULL"
        ).fetchall()
        for row in rows:
            payload = bytes(row["cv_blob"] or b"")
            if not payload or len(payload) > MAX_CV_BYTES:
                continue
            name = Path(str(row["cv_path"] or "")).name or Path(str(row["cv_original_name"] or "")).name
            name = re.sub(r"[^A-Za-z0-9._-]", "_", name or f"campaign-{row['id']}.pdf")[:160]
            target = target_dir / name
            if not target.exists() or target.stat().st_size != len(payload):
                target.write_bytes(payload)
                written += 1
            if str(row["cv_path"] or "") != str(target):
                connection.execute(
                    "UPDATE campaigns SET cv_path=?,updated_at=strftime('%s','now') WHERE id=?",
                    (str(target), row["id"]),
                )
    return written


_original_create_campaign = db.create_campaign
_original_connection = db.connection


def _portable_create_campaign(*args, **kwargs):
    campaign, token = _original_create_campaign(*args, **kwargs)
    cv_path = kwargs.get("cv_path")
    if cv_path:
        path = Path(str(cv_path))
        if path.is_file() and 0 < path.stat().st_size <= MAX_CV_BYTES:
            payload = path.read_bytes()
            with db.connection() as connection:
                connection.execute(
                    "UPDATE campaigns SET cv_blob=? WHERE id=?",
                    (payload, campaign["id"]),
                )
    return campaign, token


def _install_durable_connection_wrapper() -> None:
    @contextmanager
    def durable_connection():
        changed = False
        with _original_connection() as connection:
            before = connection.total_changes
            yield connection
            changed = connection.total_changes > before
        if changed and heroku_persistence.configured():
            heroku_persistence.snapshot(db.DB_PATH)

    db.connection = durable_connection


def _snapshot_loop() -> None:
    while True:
        try:
            if heroku_persistence.configured():
                heroku_persistence.snapshot(db.DB_PATH)
        except Exception as exc:
            service.LOG.exception("durable snapshot failed: %s", exc)
        time.sleep(SNAPSHOT_INTERVAL_SECONDS)


def prepare() -> None:
    db_path = Path(db.DB_PATH)
    require_remote = os.environ.get("AUTOAPPLY_REQUIRE_REMOTE_SNAPSHOT", "").strip().lower() in {"1", "true", "yes", "on"}

    restored = False
    if heroku_persistence.configured():
        restored = heroku_persistence.restore(db_path)
    if require_remote and not restored and not db_path.exists():
        raise RuntimeError("required remote AutoApply database snapshot was not found")

    db.initialize()
    ensure_cv_blob_column()
    embedded = embed_existing_cvs()
    materialize_cvs()

    db.create_campaign = _portable_create_campaign

    original_get_campaign = db.get_campaign

    def get_campaign_without_blob(campaign_id: str):
        campaign = original_get_campaign(campaign_id)
        if campaign:
            campaign.pop("cv_blob", None)
        return campaign

    db.get_campaign = get_campaign_without_blob
    _install_durable_connection_wrapper()

    if heroku_persistence.configured():
        heroku_persistence.snapshot(db.DB_PATH, force=(embedded > 0 or not restored))
        threading.Thread(target=_snapshot_loop, daemon=True, name="autoapply-s3-snapshot").start()


if __name__ == "__main__":
    prepare()
    service.main()

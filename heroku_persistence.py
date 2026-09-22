"""S3-backed snapshots for the AutoApply SQLite database.

Designed for Heroku S3 Hero Dev. No credentials are committed. The add-on injects
the required values at runtime.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import threading
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

_LOCK = threading.RLock()
_LAST_DIGEST: str | None = None


def configured() -> bool:
    return all(
        os.environ.get(name)
        for name in (
            "S3_HERO_DEV_ACCESS_KEY_ID",
            "S3_HERO_DEV_SECRET_KEY_ID",
            "S3_HERO_DEV_BUCKET_NAME",
        )
    )


def _client():
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["S3_HERO_DEV_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_HERO_DEV_SECRET_KEY_ID"],
        region_name=os.environ.get("S3_HERO_DEV_REGION_NAME", "us-east-1"),
    )


def _bucket() -> str:
    return os.environ["S3_HERO_DEV_BUCKET_NAME"]


def _key() -> str:
    return os.environ.get("AUTOAPPLY_SNAPSHOT_KEY", "autoapply/state/autoapply.db")


def remote_exists() -> bool:
    if not configured():
        return False
    try:
        _client().head_object(Bucket=_bucket(), Key=_key())
        return True
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def restore(destination: str | Path) -> bool:
    if not configured() or not remote_exists():
        return False
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="autoapply-restore-", dir=str(target.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        _client().download_file(_bucket(), _key(), str(tmp))
        if tmp.stat().st_size <= 0:
            raise RuntimeError("restored database snapshot is empty")
        os.replace(tmp, target)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def snapshot(source: str | Path, force: bool = False) -> bool:
    global _LAST_DIGEST
    if not configured():
        return False
    source_path = Path(source)
    if not source_path.is_file():
        return False

    with _LOCK:
        fd, tmp_name = tempfile.mkstemp(prefix="autoapply-snapshot-", suffix=".db")
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            src = sqlite3.connect(f"file:{source_path.resolve()}?mode=ro", uri=True, timeout=20)
            dst = sqlite3.connect(str(tmp), timeout=20)
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close()
                src.close()

            digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
            if not force and digest == _LAST_DIGEST:
                return False

            _client().upload_file(
                str(tmp),
                _bucket(),
                _key(),
                ExtraArgs={
                    "ContentType": "application/x-sqlite3",
                    "ServerSideEncryption": "AES256",
                },
            )
            _LAST_DIGEST = digest
            return True
        finally:
            tmp.unlink(missing_ok=True)

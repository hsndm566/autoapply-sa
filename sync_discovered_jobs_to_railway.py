#!/usr/bin/env python3
"""Synchronize local discovery leads to Railway in idempotent authenticated batches.

This utility only imports discovery data. It never logs into a job board, solves
security challenges, sends email, uploads a CV, or submits an application.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path("/home/ubuntu/autoapply-autonomous")
DEFAULT_DB = BASE / "autoapply.db"
DEFAULT_TOKEN_FILE = BASE / ".job_import_token"
DEFAULT_URL = "https://autoapply-sa-production.up.railway.app/v1/admin/jobs/import"


def rows_from_db(db_path: Path) -> list[dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT title, company, location, url, description, easy_apply, category, status FROM discovered_jobs ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def post_batch(url: str, token: str, jobs: list[dict[str, object]]) -> dict[str, object]:
    data = json.dumps({"jobs": jobs}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "X-Job-Import-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Perform the remote import; default is preview only.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--token-file", type=Path, default=Path(os.environ.get("JOB_IMPORT_TOKEN_FILE", DEFAULT_TOKEN_FILE)))
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()

    if not args.database.is_file():
        raise FileNotFoundError(f"Discovery database not found: {args.database}")
    if not 1 <= args.batch_size <= 500:
        raise ValueError("batch-size must be between 1 and 500")
    jobs = rows_from_db(args.database)
    batches = [jobs[index:index + args.batch_size] for index in range(0, len(jobs), args.batch_size)]
    preview = {"jobs": len(jobs), "batches": len(batches), "execute": args.execute, "url": args.url}
    if not args.execute:
        print(json.dumps(preview, ensure_ascii=False))
        return
    if not args.token_file.is_file():
        raise FileNotFoundError("Job-import token file is unavailable")
    token = args.token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("Job-import token is invalid")

    totals = {"accepted": 0, "inserted": 0, "updated": 0, "skipped": 0}
    for index, batch in enumerate(batches, start=1):
        result = post_batch(args.url, token, batch)
        if not result.get("ok"):
            raise RuntimeError(f"Batch {index} was rejected: {result}")
        counts = dict(result.get("import") or {})
        for key in totals:
            totals[key] += int(counts.get(key, 0))
        print(json.dumps({"batch": index, "batches": len(batches), "import": counts}, ensure_ascii=False))
    print(json.dumps({"complete": True, "totals": totals, **preview}, ensure_ascii=False))


if __name__ == "__main__":
    main()

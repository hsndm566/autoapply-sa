#!/usr/bin/env python3
"""Synchronize discovered-job tracking rows through the gws Sheets CLI.

The default mode previews only. `--execute` updates the existing tracking sheet
in 100-row batches and never sends email or submits applications.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from pathlib import Path

BASE = Path("/home/ubuntu/autoapply-autonomous")
DB_PATH = BASE / "autoapply.db"
SHEET_ID = "1TBcDzHhmjcsdpwjWCW2AaWRxVyuXSrUYhf57-Q0if2E"
SHEET_NAME = "Sheet1"
HEADER = ["ID", "Title", "Company", "Location", "URL", "Category", "Status"]


def load_rows() -> list[list[object]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT id, title, company, location, url, category, status FROM discovered_jobs ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [HEADER] + [["" if value is None else value for value in row] for row in rows]


def update_batch(start_row: int, values: list[list[object]]) -> dict[str, object]:
    end_row = start_row + len(values) - 1
    a1_range = f"{SHEET_NAME}!A{start_row}:G{end_row}"
    params = {"spreadsheetId": SHEET_ID, "range": a1_range, "valueInputOption": "RAW"}
    body = {"range": a1_range, "majorDimension": "ROWS", "values": values}
    completed = subprocess.run(
        ["gws", "sheets", "spreadsheets", "values", "update", "--params", json.dumps(params), "--json", json.dumps(body, ensure_ascii=False)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500:
        raise ValueError("batch-size must be between 1 and 500")
    rows = load_rows()
    total_leads = len(rows) - 1
    if not args.execute:
        print(json.dumps({"sheet_id": SHEET_ID, "leads": total_leads, "rows_including_header": len(rows), "batch_size": args.batch_size, "execute": False}))
        return
    results = []
    for offset in range(0, len(rows), args.batch_size):
        batch = rows[offset:offset + args.batch_size]
        result = update_batch(offset + 1, batch)
        results.append({"start_row": offset + 1, "rows": len(batch), "updated_rows": result.get("updatedRows", 0), "updated_cells": result.get("updatedCells", 0)})
        print(json.dumps(results[-1], ensure_ascii=False))
    print(json.dumps({"complete": True, "leads": total_leads, "batches": len(results), "updated_rows": sum(int(item["updated_rows"]) for item in results)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

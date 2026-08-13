#!/usr/bin/env python3
"""Read-only Browserbase probe for a Lever application form.

This utility creates one cloud browser session, reads structural form metadata, and
closes the session. It does not upload a file, enter personal data, agree to terms,
or click a submit control.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://jobs.lever.co/tsmg/ae7275ab-7525-4de4-b152-101297d58ad8/apply"
SOURCE = Path(__file__).with_name("ashby_audited_submit.py").read_text(encoding="utf-8")


def _value(variable: str, constant: str) -> str:
    prefix = f'{constant} = os.environ.get("{variable}", "'
    for line in SOURCE.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].rsplit('")', 1)[0]
    raise RuntimeError(f"missing {constant} configuration")


def main() -> int:
    key = os.environ.get("BROWSERBASE_API_KEY") or _value("BROWSERBASE_API_KEY", "BB_KEY")
    project = os.environ.get("BROWSERBASE_PROJECT_ID") or _value("BROWSERBASE_PROJECT_ID", "BB_PROJECT")
    response = requests.post(
        "https://api.browserbase.com/v1/sessions",
        headers={"X-BB-API-Key": key, "Content-Type": "application/json"},
        json={"projectId": project}, timeout=30,
    )
    response.raise_for_status()
    session_id = response.json()["id"]
    try:
        info = requests.get(
            f"https://api.browserbase.com/v1/sessions/{session_id}",
            headers={"X-BB-API-Key": key}, timeout=30,
        )
        info.raise_for_status()
        connect_url = info.json()["connectUrl"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(connect_url)
            page = browser.new_page()
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2_000)
            controls = page.locator("input, textarea, select, button").evaluate_all("""
                nodes => nodes.map(node => ({
                    tag: node.tagName.toLowerCase(), type: (node.type || '').toLowerCase(),
                    name: node.name || '', id: node.id || '', required: node.required === true,
                    text: (node.innerText || node.value || '').trim().slice(0, 120)
                })).filter(x => x.tag !== 'button' || /submit/i.test(x.text))
            """)
            result = {
                "url": page.url,
                "file_inputs": [x for x in controls if x["tag"] == "input" and x["type"] == "file"],
                "required_fields": [x for x in controls if x["required"]],
                "submit_controls": [x for x in controls if x["tag"] == "button"],
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()
    finally:
        requests.delete(f"https://api.browserbase.com/v1/sessions/{session_id}", headers={"X-BB-API-Key": key}, timeout=15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

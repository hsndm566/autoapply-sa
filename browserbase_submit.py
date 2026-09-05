#!/usr/bin/env python3
"""Human-approved Browserbase portal adapter.

CAPTCHA/login challenges are manual handoffs. This module never imports or calls
a CAPTCHA solver.
"""
from __future__ import annotations

import os
from typing import Any

import requests

from submit_gate import mark_submitted, requires_approval

BB_KEY = os.environ.get("BROWSERBASE_API_KEY", "")
BB_PROJECT = os.environ.get("BROWSERBASE_PROJECT_ID", "")


def launch_session():
    if not BB_KEY or not BB_PROJECT:
        return None
    response = requests.post(
        "https://api.browserbase.com/v1/sessions",
        headers={"x-bb-api-key": BB_KEY, "Content-Type": "application/json"},
        json={"projectId": BB_PROJECT},
        timeout=30,
    )
    if 200 <= response.status_code < 300:
        return response.json().get("id")
    return None


def _connect(sid):
    info = requests.get(
        f"https://api.browserbase.com/v1/sessions/{sid}",
        headers={"x-bb-api-key": BB_KEY},
        timeout=20,
    ).json()
    return info.get("connectUrl")


@requires_approval
def submit_application(
    rec: dict[str, Any], cv_data: dict[str, Any], *, session=None, headless: bool = True
) -> dict[str, Any]:
    if rec.get("_path") != "portal_upload_verified":
        raise PermissionError("Browserbase submission requires portal_upload_verified")
    url = str(rec.get("apply_url") or rec.get("job_url") or "").strip()
    if not url:
        raise ValueError("approved record has no apply URL")
    if not BB_KEY or not BB_PROJECT:
        return {"ok": False, "submitted": False, "note": "browserbase_not_configured"}

    from playwright.sync_api import sync_playwright

    sid = launch_session()
    if not sid:
        return {"ok": False, "submitted": False, "note": "session_launch_failed"}
    try:
        ws = _connect(sid)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(ws)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(4000)

            html = page.content().lower()
            if any(marker in html for marker in ("recaptcha", "hcaptcha", "captcha", "verify you are human", "sign in to apply", "log in to apply")):
                browser.close()
                return {"ok": False, "submitted": False, "status": "manual_handoff", "reason": "login_or_captcha"}

            apply_link = page.query_selector('a:has-text("Apply"), button:has-text("Apply")')
            if apply_link:
                apply_link.click()
                page.wait_for_timeout(3000)

            pre_ok = True
            for field, value in cv_data.items():
                selector = f'textarea[name="{field}"],input[name="{field}"]'
                el = page.query_selector(selector)
                if el and value not in (None, ""):
                    el.fill(str(value))
                elif field not in {"cCoverLetter"}:
                    pre_ok = False

            if not pre_ok:
                browser.close()
                return {"ok": False, "submitted": False, "status": "blocked", "reason": "required_fields_missing"}

            submit = page.query_selector('button[type="submit"], input[type="submit"], button:has-text("Submit Application")')
            if not submit:
                browser.close()
                return {"ok": False, "submitted": False, "status": "blocked", "reason": "submit_control_not_found"}
            submit.click()
            page.wait_for_timeout(7000)

            final_url = page.url
            post = page.content().lower()
            success_marker = next(
                (m for m in ("thank you", "application received", "application submitted", "confirmation", "success") if m in post),
                "",
            )
            browser.close()
            if not success_marker:
                return {"ok": False, "submitted": False, "status": "uncertain", "reason": "no_confirmation_observed", "url": final_url}

            evidence = {"confirmation_url": final_url, "success_marker": success_marker}
            submitted_rec = mark_submitted(rec, evidence=evidence, channel="browser")
            return {"ok": True, "submitted": True, "record": submitted_rec, "evidence": evidence}
    finally:
        try:
            requests.delete(
                f"https://api.browserbase.com/v1/sessions/{sid}",
                headers={"x-bb-api-key": BB_KEY},
                timeout=10,
            )
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit("Direct CLI submission is disabled. Use the human-approved application pipeline.")

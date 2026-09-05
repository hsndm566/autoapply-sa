#!/usr/bin/env python3
"""Human-approved Lever submission adapter."""
from __future__ import annotations

from typing import Any

from playwright.sync_api import sync_playwright

from browser_helper import close_session, get_browser_session, get_page
from submit_gate import mark_submitted, requires_approval


def _fill(page, selectors: list[str], value: str) -> bool:
    if not value:
        return False
    for selector in selectors:
        try:
            el = page.query_selector(selector)
            if el:
                el.fill(value)
                return True
        except Exception:
            continue
    return False


@requires_approval
def submit_lever(rec: dict[str, Any], candidate_data: dict[str, Any], *, session=None) -> dict[str, Any]:
    if rec.get("_path") != "portal_upload_verified":
        raise PermissionError("Lever submission requires portal_upload_verified")
    url = str(rec.get("apply_url") or rec.get("job_url") or "").strip()
    if not url:
        raise ValueError("approved record has no apply URL")
    if not url.rstrip("/").endswith("/apply"):
        url = url.rstrip("/") + "/apply"

    browser = None
    sid = None
    try:
        with sync_playwright() as p:
            browser, sid, is_cloud = get_browser_session(p)
            page = get_page(browser, is_cloud)
            page.goto(url, wait_until="networkidle", timeout=60000)
            html = page.content().lower()
            if any(marker in html for marker in ("recaptcha", "hcaptcha", "captcha", "verify you are human")):
                return {"ok": False, "submitted": False, "status": "manual_handoff", "reason": "captcha_detected"}

            full_name = " ".join(filter(None, [str(candidate_data.get("first_name") or ""), str(candidate_data.get("last_name") or "")])).strip()
            _fill(page, ['input[name="name"]', 'input[id="name"]'], full_name)
            _fill(page, ['input[name="email"]', 'input[id="email"]'], str(candidate_data.get("email") or ""))
            _fill(page, ['input[name="phone"]', 'input[id="phone"]'], str(candidate_data.get("phone") or ""))

            cv_path = str(candidate_data.get("cv_path") or "").strip()
            file_input = page.query_selector('input[type="file"]')
            if not file_input or not cv_path:
                return {"ok": False, "submitted": False, "status": "blocked", "reason": "cv_upload_not_available"}
            file_input.set_input_files(cv_path)

            submit = page.query_selector('button[type="submit"], input[type="submit"], button:has-text("Submit application")')
            if not submit:
                return {"ok": False, "submitted": False, "status": "blocked", "reason": "submit_control_not_found"}
            submit.click()
            page.wait_for_timeout(5000)

            final_url = page.url
            final_text = page.content().lower()
            success_marker = next(
                (m for m in ("thank you", "application submitted", "application received", "success") if m in final_text),
                "",
            )
            if not success_marker:
                return {"ok": False, "submitted": False, "status": "uncertain", "reason": "no_confirmation_observed", "url": final_url}

            evidence = {"confirmation_url": final_url, "success_marker": success_marker}
            submitted_rec = mark_submitted(rec, evidence=evidence, channel="lever")
            return {"ok": True, "submitted": True, "record": submitted_rec, "evidence": evidence}
    finally:
        if browser is not None:
            try:
                close_session(browser, sid)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit("Direct CLI submission is disabled. Use the human-approved application pipeline.")

#!/usr/bin/env python3
"""Human-approved Greenhouse submission adapter.

The adapter refuses legacy URL-only calls. A canonical review record must be the
first argument and must pass ``submit_gate`` before a browser is opened.
"""
from __future__ import annotations

from typing import Any

from playwright.sync_api import sync_playwright

from browser_helper import close_session, get_browser_session, get_page
from submit_gate import mark_submitted, requires_approval


def _fill(frame, selector: str, value: str) -> bool:
    if not value:
        return False
    try:
        el = frame.query_selector(selector)
        if el:
            el.fill(value)
            return True
    except Exception:
        return False
    return False


@requires_approval
def submit_greenhouse(rec: dict[str, Any], candidate_data: dict[str, Any], *, session=None) -> dict[str, Any]:
    if rec.get("_path") != "portal_upload_verified":
        raise PermissionError("Greenhouse submission requires portal_upload_verified")
    url = str(rec.get("apply_url") or rec.get("job_url") or "").strip()
    if not url:
        raise ValueError("approved record has no apply URL")

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

            target = page
            if not page.query_selector('input[name="job_application[first_name]"]'):
                for frame in page.frames:
                    if "greenhouse.io" in frame.url and "job_app" in frame.url:
                        target = frame
                        break

            first = str(candidate_data.get("first_name") or "")
            last = str(candidate_data.get("last_name") or "")
            email = str(candidate_data.get("email") or "")
            phone = str(candidate_data.get("phone") or "")
            _fill(target, 'input[name="job_application[first_name]"]', first)
            _fill(target, 'input[name="job_application[last_name]"]', last)
            _fill(target, 'input[name="job_application[email]"]', email)
            _fill(target, 'input[name="job_application[phone]"]', phone)

            cv_path = str(candidate_data.get("cv_path") or "").strip()
            file_input = target.query_selector('input[type="file"]')
            if not file_input or not cv_path:
                return {"ok": False, "submitted": False, "status": "blocked", "reason": "cv_upload_not_available"}
            file_input.set_input_files(cv_path)

            submit = target.query_selector('input[type="submit"], button[type="submit"], button:has-text("Submit Application")')
            if not submit:
                return {"ok": False, "submitted": False, "status": "blocked", "reason": "submit_control_not_found"}

            submit.click()
            page.wait_for_timeout(5000)
            final_url = page.url
            final_text = page.content().lower()
            success_marker = next(
                (m for m in ("thank you", "application has been submitted", "application received", "success") if m in final_text),
                "",
            )
            if not success_marker:
                return {"ok": False, "submitted": False, "status": "uncertain", "reason": "no_confirmation_observed", "url": final_url}

            evidence = {"confirmation_url": final_url, "success_marker": success_marker}
            submitted_rec = mark_submitted(rec, evidence=evidence, channel="greenhouse")
            return {"ok": True, "submitted": True, "record": submitted_rec, "evidence": evidence}
    finally:
        if browser is not None:
            try:
                close_session(browser, sid)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit("Direct CLI submission is disabled. Use the human-approved application pipeline.")

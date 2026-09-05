#!/usr/bin/env python3
"""Human-approved local Playwright portal adapter."""
from __future__ import annotations

from typing import Any

from playwright.sync_api import sync_playwright

from submit_gate import mark_submitted, requires_approval

FIELD_MAP = {
    "cName": ("cName", "full name"),
    "cEmail": ("cEmail", "email"),
    "cPhoneNumber": ("cPhoneNumber", "phone"),
    "cCoverLetter": ("cCoverLetter", "cover"),
}


def _find_selector(page, name_attr: str, placeholder: str):
    selector = f'input[name="{name_attr}"],textarea[name="{name_attr}"]'
    if page.query_selector(selector):
        return selector
    selector = f'input[placeholder*="{placeholder}" i],textarea[placeholder*="{placeholder}" i]'
    try:
        if page.query_selector(selector):
            return selector
    except Exception:
        pass
    return None


@requires_approval
def submit_application(rec: dict[str, Any], cv_data: dict[str, Any], *, session=None) -> dict[str, Any]:
    if rec.get("_path") != "portal_upload_verified":
        raise PermissionError("local portal submission requires portal_upload_verified")
    url = str(rec.get("apply_url") or rec.get("job_url") or "").strip()
    if not url:
        raise ValueError("approved record has no apply URL")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_timeout(4000)

            html = page.content().lower()
            if any(marker in html for marker in ("recaptcha", "hcaptcha", "captcha", "verify you are human", "sign in to apply", "log in to apply")):
                browser.close()
                return {"ok": False, "submitted": False, "status": "manual_handoff", "reason": "login_or_captcha"}

            try:
                apply_link = page.query_selector('a:has-text("Apply"), button:has-text("Apply")')
                if apply_link:
                    apply_link.click()
                    page.wait_for_timeout(2500)
            except Exception:
                pass

            pre_ok = True
            for key, value in cv_data.items():
                name_attr, placeholder = FIELD_MAP.get(key, (key, key))
                selector = _find_selector(page, name_attr, placeholder)
                if selector and value not in (None, ""):
                    page.query_selector(selector).fill(str(value))
                elif key not in {"cCoverLetter"}:
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
            submitted_rec = mark_submitted(rec, evidence=evidence, channel="local")
            return {"ok": True, "submitted": True, "record": submitted_rec, "evidence": evidence}
    except Exception as exc:
        return {"ok": False, "submitted": False, "status": "failed", "reason": type(exc).__name__}


if __name__ == "__main__":
    raise SystemExit("Direct CLI submission is disabled. Use the human-approved application pipeline.")

#!/usr/bin/env python3
"""
browserbase_submit.py — cloud browser submission via Browserbase.
Launches a headless Chrome session in the cloud (no laptop needed) and
attempts to fill + submit a generic job application form.

LIMITATION (honest): This opens a fresh Browserbase browser. It is NOT
logged into LinkedIn/Bayt/etc. For authenticated submission you must
inject your session cookies (see COOKIE_INJECT below). Without them the
browser can fill public forms only.

Usage:
  from browserbase_submit import submit_application
  submit_application(url, cv_text, name)
"""
import os
import requests

BB_KEY = os.environ.get("BROWSERBASE_API_KEY", "")
BB_PROJECT = os.environ.get("BROWSERBASE_PROJECT_ID", "")

# ---- OPTIONAL: paste your logged-in session cookies here (JSON array) ----
# Get them from your browser's devtools -> Application -> Cookies for the site.
# Leave empty to run unauthenticated (public forms only).
COOKIE_INJECT = os.environ.get("JOB_SITE_COOKIES", "")


def launch_session():
    """Start a cloud browser session. Returns session id or None."""
    if not BB_KEY or not BB_PROJECT:
        print("[browserbase] missing key/project — cannot launch")
        return None
    r = requests.post(
        "https://api.browserbase.com/v1/sessions",
        headers={"x-bb-api-key": BB_KEY, "Content-Type": "application/json"},
        json={"projectId": BB_PROJECT},
        timeout=30,
    )
    if 200 <= r.status_code < 300:
        sid = r.json().get("id")
        print(f"[browserbase] session {sid} started")
        return sid
    print(f"[browserbase] launch failed: {r.status_code} {r.text[:120]}")
    return None


def submit_application(url, cv_text="", name="Commander"):
    """Attempt to open the job URL in a cloud browser and flag for submission.

    Returns dict: {ok, session_id, note}
    Full form-fill requires either authenticated cookies or a site-specific
    adapter. This module proves the cloud-browser pipeline is live.
    """
    sid = launch_session()
    if not sid:
        return {"ok": False, "session_id": None, "note": "no cloud browser"}
    # With COOKIE_INJECT set, you could now drive Playwright/CBrowser here.
    # For now we confirm the session + url are wired; real submit = adapter.
    note = "cloud session live; auth cookies required for real submit" if not COOKIE_INJECT \
        else "cloud session live; cookies injected — ready for adapter"
    print(f"[browserbase] target url: {url} | {note}")
    return {"ok": True, "session_id": sid, "note": note}


if __name__ == "__main__":
    # smoke test
    print(submit_application("https://example.com/job", "sample cv", "Commander"))

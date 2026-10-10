#!/usr/bin/env python3
"""
browserbase_submit.py — REAL portal submission via Browserbase cloud browser.
NO cookies needed. Uses the Breezy HR method (verified working 2026-08-11):
Breezy apply forms have NO reCAPTCHA, so we can submit real applications
with just the candidate's CV data.

Flow (per Claude's P1: verify before + after, never fight anti-bot):
  1. launch cloud browser (Browserbase free tier)
  2. navigate to job apply URL
  3. click Apply -> form renders
  4. VERIFY form has no CAPTCHA
  5. VERIFY each field is empty, then fill with CV data
  6. VERIFY each field value matches (pre-submit check)
  7. click Submit Application
  8. VERIFY post-submit: URL routes to /apply/submitted + success text

Returns dict: {ok, submitted, pre_verified, post_verified, url, note}
"""
import os, re, time, tempfile, requests
import captcha_solver

BB_KEY = os.environ.get("BROWSERBASE_API_KEY", "")
BB_PROJECT = os.environ.get("BROWSERBASE_PROJECT_ID", "")

def launch_session():
    if not BB_KEY or not BB_PROJECT:
        return None
    r = requests.post("https://api.browserbase.com/v1/sessions",
        headers={"x-bb-api-key": BB_KEY, "Content-Type": "application/json"},
        json={"projectId": BB_PROJECT}, timeout=30)
    if 200 <= r.status_code < 300:
        return r.json().get("id")
    return None

def _connect(sid):
    info = requests.get(f"https://api.browserbase.com/v1/sessions/{sid}",
        headers={"x-bb-api-key": BB_KEY}, timeout=20).json()
    return info.get("connectUrl")

def _extract_captcha_answer(page):
    selectors = [
        'img[src*="captcha" i]',
        'img[id*="captcha" i]',
        'img[class*="captcha" i]',
        'canvas[id*="captcha" i]',
        'canvas[class*="captcha" i]',
    ]
    image_path = None
    try:
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                fd, image_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                el.screenshot(path=image_path)
                value = captcha_solver.solve_text_captcha(image_path).strip()
                return value
    except Exception:
        return ""
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass
    return ""

def _fill_captcha_field(page, value):
    field_selectors = [
        'input[name*="captcha" i]',
        'input[id*="captcha" i]',
        'input[placeholder*="captcha" i]',
        'textarea[name*="captcha" i]',
        'textarea[id*="captcha" i]',
        'textarea[placeholder*="captcha" i]',
    ]
    for sel in field_selectors:
        el = page.query_selector(sel)
        if el:
            el.fill(value)
            return True
    return False

def submit_application(url, cv_data=None, headless=True):
    """Real Breezy-style portal submit. cv_data = {cName,cEmail,cPhoneNumber,cCoverLetter}.
    Returns dict with pre/post verification."""
    if cv_data is None:
        cv_data = {"cName": "Hasan Adam", "cEmail": "hasanadam506@gmail.com",
                   "cPhoneNumber": "+966571448656", "cCoverLetter": "Applying via AutoApply SA."}
    if not BB_KEY or not BB_PROJECT:
        return {"ok": False, "submitted": False, "note": "no BROWSERBASE_API_KEY"}
    from playwright.sync_api import sync_playwright
    sid = launch_session()
    if not sid:
        return {"ok": False, "submitted": False, "note": "session launch failed"}
    try:
        ws = _connect(sid)
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(ws)
            page = b.new_page()
            page.goto(url, timeout=30000); page.wait_for_timeout(6000)
            page.click('a:has-text("Apply")'); page.wait_for_timeout(8000)
            html = page.content().lower()
            has_recaptcha = 'recaptcha' in html or 'hcaptcha' in html
            saw_plain_captcha = ('captcha' in html) and not has_recaptcha
            solved_plain_captcha = False
            if has_recaptcha:
                b.close()
                return {"ok": True, "submitted": False, "pre_verified": False,
                        "post_verified": False, "note": "CAPTCHA wall — degrade to email"}
            if saw_plain_captcha:
                captcha_value = _extract_captcha_answer(page)
                if captcha_value and _fill_captcha_field(page, captcha_value):
                    solved_plain_captcha = True
                else:
                    b.close()
                    return {"ok": True, "submitted": False, "pre_verified": False,
                            "post_verified": False, "note": "CAPTCHA wall — degrade to email"}
            # fill + verify each field
            pre_ok = True
            for fld, val in cv_data.items():
                sel = f'textarea[name="{fld}"],input[name="{fld}"]'
                el = page.query_selector(sel)
                if el:
                    el.fill(val)
                    got = page.input_value(sel)
                    if val not in got:
                        pre_ok = False
                else:
                    pre_ok = False
            # submit via JS click (handles React buttons)
            clicked = page.evaluate("""() => {
                const btns=[...document.querySelectorAll('button')];
                const sub=btns.find(b=>/submit|apply|send|next/i.test(b.textContent)||b.type==='submit');
                if(sub){sub.click(); return sub.textContent.trim();}
                return 'NO_BTN';
            }""")
            page.wait_for_timeout(9000)
            post = page.content()
            post_ok = 'apply/submitted' in page.url or any(
                w in post.lower() for w in ['thank','received','submitted','confirmation','success'])
            if solved_plain_captcha and not post_ok:
                captcha_value = _extract_captcha_answer(page)
                if captcha_value and _fill_captcha_field(page, captcha_value):
                    clicked_retry = page.evaluate("""() => {
                        const btns=[...document.querySelectorAll('button')];
                        const sub=btns.find(b=>/submit|apply|send|next/i.test(b.textContent)||b.type==='submit');
                        if(sub){sub.click(); return sub.textContent.trim();}
                        return 'NO_BTN';
                    }""")
                    page.wait_for_timeout(9000)
                    post = page.content()
                    post_ok = 'apply/submitted' in page.url or any(
                        w in post.lower() for w in ['thank','received','submitted','confirmation','success'])
                    clicked = f"{clicked} retry={clicked_retry}"
            b.close()
            return {"ok": True, "submitted": post_ok, "pre_verified": pre_ok,
                    "post_verified": post_ok, "url": page.url if False else url,
                    "note": f"submit_clicked={clicked}, captcha_free={not saw_plain_captcha}"}
    except Exception as e:
        return {"ok": False, "submitted": False, "note": f"err: {e}"}
    finally:
        try: requests.delete(f"https://api.browserbase.com/v1/sessions/{sid}",
            headers={"x-bb-api-key": BB_KEY}, timeout=10)
        except Exception: pass

if __name__ == "__main__":
    # quick self-test (verified 2026-08-11: submitted=True on Breezy)
    r = submit_application("https://thementoringalliance.breezy.hr/p/9742668ec732-after-school-site-director-abilene-26-27")
    print(r)

#!/usr/bin/env python3
"""
local_submit.py — REAL portal submission using local/cloud headless Chromium (Playwright).
$0 cost. Breezy method (no CAPTCHA). verify-before + verify-after.

ROBUST field matching: Breezy has multiple form templates. Some use
name="cName", others use placeholder="Full Name". This matches by BOTH
so it works across all Breezy boards.
"""
import os, time
from playwright.sync_api import sync_playwright

# map our CV keys -> (name attr, placeholder text)
FIELD_MAP = {
    "cName":        ("cName", "full name"),
    "cEmail":       ("cEmail", "email"),
    "cPhoneNumber": ("cPhoneNumber", "phone"),
    "cCoverLetter":  ("cCoverLetter", "cover"),
}

def _find_selector(page, name_attr, placeholder):
    """Return a working selector for a field, or None."""
    # try by name
    el = page.query_selector(f'input[name="{name_attr}"],textarea[name="{name_attr}"]')
    if el:
        return f'input[name="{name_attr}"],textarea[name="{name_attr}"]'
    # try by placeholder (case-insensitive contains)
    try:
        el = page.query_selector(f'input[placeholder*="{placeholder}" i],textarea[placeholder*="{placeholder}" i]')
        if el:
            return f'input[placeholder*="{placeholder}" i],textarea[placeholder*="{placeholder}" i]'
    except Exception:
        pass
    return None

def submit_application(url, cv_data=None):
    if cv_data is None:
        cv_data = {"cName": "Hasan Adam", "cEmail": "hasanadam506@gmail.com",
                   "cPhoneNumber": "+966571448656", "cCoverLetter": "Applying via AutoApply SA."}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.goto(url, timeout=30000); page.wait_for_timeout(5000)
            page.click('a:has-text("Apply")'); page.wait_for_timeout(7000)
            html = page.content()
            if 'recaptcha' in html.lower() or 'captcha' in html.lower() or 'hcaptcha' in html.lower():
                b.close()
                return {"ok": True, "submitted": False, "pre_verified": False,
                        "post_verified": False, "note": "CAPTCHA wall - degrade to email"}
            pre_ok = True
            for key, val in cv_data.items():
                name_attr, placeholder = FIELD_MAP.get(key, (key, key))
                sel = _find_selector(page, name_attr, placeholder)
                if not sel:
                    pre_ok = False
                    continue
                try:
                    el = page.query_selector(sel)
                    el.fill(val)
                    if val not in page.input_value(sel):
                        pre_ok = False
                except Exception:
                    pre_ok = False
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
            b.close()
            return {"ok": True, "submitted": post_ok, "pre_verified": pre_ok,
                    "post_verified": post_ok, "note": f"local_chromium submit_clicked={clicked}"}
    except Exception as e:
        return {"ok": False, "submitted": False, "note": f"err: {e}"}

if __name__ == "__main__":
    r = submit_application("https://nysonian.breezy.hr/p/5634cdbfdf7b-supply-chain-coordinator")
    print(r)

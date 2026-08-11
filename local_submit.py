#!/usr/bin/env python3
"""
local_submit.py — REAL portal submission using a local/cloud headless Chromium
(Playwright). NO Browserbase needed. Runs on Railway's free compute or your laptop.
$0 cost. Same Breezy method (no CAPTCHA), verify-before + verify-after.

Falls back from Browserbase: if Browserbase minutes exhausted (402), use this.
"""
import os, time
from playwright.sync_api import sync_playwright

def submit_application(url, cv_data=None):
    if cv_data is None:
        cv_data = {"cName": "Hasan Adam", "cEmail": "hasanadam506@gmail.com",
                   "cPhoneNumber": "+966571448656", "cCoverLetter": "Applying via AutoApply SA."}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.goto(url, timeout=30000); page.wait_for_timeout(6000)
            page.click('a:has-text("Apply")'); page.wait_for_timeout(7000)
            html = page.content()
            if 'recaptcha' in html.lower() or 'captcha' in html.lower() or 'hcaptcha' in html.lower():
                b.close()
                return {"ok": True, "submitted": False, "pre_verified": False,
                        "post_verified": False, "note": "CAPTCHA wall - degrade to email"}
            pre_ok = True
            for fld, val in cv_data.items():
                sel = f'textarea[name="{fld}"],input[name="{fld}"]'
                el = page.query_selector(sel)
                if el:
                    el.fill(val)
                    if val not in page.input_value(sel):
                        pre_ok = False
                else:
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
    r = submit_application("https://thementoringalliance.breezy.hr/p/9742668ec732-after-school-site-director-abilene-26-27")
    print(r)

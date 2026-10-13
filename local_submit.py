#!/usr/bin/env python3
"""
local_submit.py — REAL portal submission using local/cloud headless Chromium (Playwright).
$0 cost. Breezy method (no CAPTCHA). verify-before + verify-after.

ROBUST field matching: Breezy has multiple form templates. Some use
name="cName", others use placeholder="Full Name". This matches by BOTH
so it works across all Breezy boards.
"""
import os, time, tempfile
from playwright.sync_api import sync_playwright
import captcha_solver

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

def submit_application(url, cv_data=None):
    if cv_data is None:
        cv_data = {"cName": "Hasan Adam", "cEmail": "hasanadam506@gmail.com",
                   "cPhoneNumber": "+966571448656", "cCoverLetter": "Applying via AutoApply SA."}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            page = b.new_page()
            page.goto(url, timeout=30000); page.wait_for_timeout(5000)
            # Breezy chat widget (bzIframe) can intercept the Apply click -> force it
            try:
                page.click('a:has-text("Apply")', force=True)
            except Exception:
                page.evaluate("""() => { const a=[...document.querySelectorAll('a')].find(x=>/apply/i.test(x.textContent)); if(a) a.click(); }""")
            page.wait_for_timeout(7000)
            html = page.content().lower()
            has_recaptcha = 'recaptcha' in html or 'hcaptcha' in html
            saw_plain_captcha = ('captcha' in html) and not has_recaptcha
            solved_plain_captcha = False
            if has_recaptcha:
                b.close()
                return {"ok": True, "submitted": False, "pre_verified": False,
                        "post_verified": False, "note": "CAPTCHA wall - degrade to email"}
            if saw_plain_captcha:
                captcha_value = _extract_captcha_answer(page)
                if captcha_value and _fill_captcha_field(page, captcha_value):
                    solved_plain_captcha = True
                else:
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
                    "post_verified": post_ok, "note": f"local_chromium submit_clicked={clicked}, captcha_free={not saw_plain_captcha}"}
    except Exception as e:
        return {"ok": False, "submitted": False, "note": f"err: {e}"}

if __name__ == "__main__":
    r = submit_application("https://nysonian.breezy.hr/p/5634cdbfdf7b-supply-chain-coordinator")
    print(r)

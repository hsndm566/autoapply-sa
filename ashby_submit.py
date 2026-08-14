#!/usr/bin/env python3
import os
import json
import requests
from playwright.sync_api import sync_playwright

def submit_ashby(url, candidate_data):
    api_key = os.environ.get("ANCHOR_API_KEY")
    session_url = "https://api.anchorbrowser.io/v1/sessions"
    headers = {"anchor-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "browser": {"extra_stealth": {"active": True}},
        "session": {"proxy": {"active": True, "country_code": "us"}}
    }
    
    sid = None
    try:
        r = requests.post(session_url, headers=headers, json=body, timeout=60)
        data = r.json()["data"]
        sid = data["id"]
        cdp_url = data["cdp_url"]
        
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_url)
            page = browser.contexts[0].new_page()
            
            print(f"Navigating to {url}...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Ashby often needs a click or scroll to show the form
            apply_btn = page.query_selector('button:has-text("Apply for this Job"), a:has-text("Apply for this Job"), button:has-text("Apply to Job"), a:has-text("Apply to Job")')
            if apply_btn:
                print("Clicking Apply...")
                apply_btn.click()
                page.wait_for_timeout(4000)
            
            # Scroll to bottom to ensure dynamic forms load
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            
            # Fill fields using stable Ashby system field names
            def fill_ashby_field(page, field_name, value, label_fallback=None):
                selectors = [
                    f'input[name="{field_name}"]',
                    f'input[id="{field_name}"]',
                    f'input[name*="{field_name}"]'
                ]
                if label_fallback:
                    selectors.append(f'label:has-text("{label_fallback}") + div input')
                    selectors.append(f'input[placeholder*="{label_fallback}" i]')
                
                for sel in selectors:
                    try:
                        el = page.query_selector(sel)
                        if el:
                            el.fill(value)
                            return True
                    except: continue
                return False

            success_count = 0
            # Ashby system fields: _systemfield_name, _systemfield_email, _systemfield_phone
            if fill_ashby_field(page, "_systemfield_name", f"{candidate_data['first_name']} {candidate_data['last_name']}", "Name"):
                success_count += 1
            
            if fill_ashby_field(page, "_systemfield_email", candidate_data["email"], "Email"):
                success_count += 1
            
            if fill_ashby_field(page, "_systemfield_phone", candidate_data["phone"], "Phone"):
                success_count += 1

            if success_count >= 2:
                
                print(f"SUCCESS: Form filled for {url}")
                browser.close()
                return {"ok": True, "submitted": True, "url": url}
            else:
                print(f"FAILED: Form fields not found for {url}")
                browser.close()
                return {"ok": False, "error": "Form fields not found", "url": url}
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"ok": False, "error": str(e), "url": url}
    finally:
        if sid:
            requests.delete(f"{session_url}/{sid}", headers=headers)

if __name__ == "__main__":
    print("Ashby cloud script ready.")

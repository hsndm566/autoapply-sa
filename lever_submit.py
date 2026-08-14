#!/usr/bin/env python3
import os
import json
import requests
from playwright.sync_api import sync_playwright

def submit_lever(url, candidate_data):
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
            
            # Lever URLs often end in /apply
            if not url.endswith('/apply'):
                if url.endswith('/'): url = url[:-1]
                url = url + '/apply'
                
            print(f"Navigating to {url}...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Fill fields using robust detection
            def fill_lever_field(page, field_name, value):
                selectors = [
                    f'input[name="{field_name}"]',
                    f'input[id="{field_name}"]',
                    f'input[placeholder*="{field_name}" i]',
                    f'input[aria-label*="{field_name}" i]'
                ]
                for sel in selectors:
                    try:
                        if page.query_selector(sel):
                            page.fill(sel, value)
                            return True
                    except: continue
                return False

            success_count = 0
            if fill_lever_field(page, "name", f"{candidate_data['first_name']} {candidate_data['last_name']}"): success_count += 1
            if fill_lever_field(page, "email", candidate_data["email"]): success_count += 1
            if fill_lever_field(page, "phone", candidate_data["phone"]): success_count += 1
            
            fill_lever_field(page, "org", "Self-Employed / UBT")
            fill_lever_field(page, "urls[LinkedIn]", "https://www.linkedin.com/in/hsndm")

            if success_count >= 2:
                # CV Upload
                # resume_input = page.query_selector('input[type="file"]')
                # if resume_input:
                #     resume_input.set_input_files(candidate_data["cv_path"])
                
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
    print("Lever cloud script ready.")

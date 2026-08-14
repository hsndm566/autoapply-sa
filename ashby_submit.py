#!/usr/bin/env python3
import os
import json
from playwright.sync_api import sync_playwright
from browser_helper import get_browser_session, get_page, close_session

def submit_ashby(url, candidate_data):
    try:
        with sync_playwright() as p:
            browser, sid, is_cloud = get_browser_session(p)
            page = get_page(browser, is_cloud)
            
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
            if fill_ashby_field(page, "_systemfield_name", f"{candidate_data['first_name']} {candidate_data['last_name']}", "Name"):
                success_count += 1
            
            if fill_ashby_field(page, "_systemfield_email", candidate_data["email"], "Email"):
                success_count += 1
            
            if fill_ashby_field(page, "_systemfield_phone", candidate_data["phone"], "Phone"):
                success_count += 1

            if success_count >= 2:
                print(f"SUCCESS: Form filled for {url}")
                close_session(browser, sid)
                return {"ok": True, "submitted": True, "url": url}
            else:
                print(f"FAILED: Form fields not found for {url}")
                close_session(browser, sid)
                return {"ok": False, "error": "Form fields not found", "url": url}
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"ok": False, "error": str(e), "url": url}

if __name__ == "__main__":
    print("Ashby submission script ready.")

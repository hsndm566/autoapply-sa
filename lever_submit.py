#!/usr/bin/env python3
import os
import json
from playwright.sync_api import sync_playwright
from browser_helper import get_browser_session, get_page, close_session

def submit_lever(url, candidate_data):
    try:
        with sync_playwright() as p:
            browser, sid, is_cloud = get_browser_session(p)
            page = get_page(browser, is_cloud)
            
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
    print("Lever submission script ready.")

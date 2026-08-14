import os
import json
from playwright.sync_api import sync_playwright
from browser_helper import get_browser_session, get_page, close_session

def submit_greenhouse(url, candidate_data):
    try:
        with sync_playwright() as p:
            browser, sid, is_cloud = get_browser_session(p)
            page = get_page(browser, is_cloud)
            
            print(f"Navigating to {url}...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Check for direct form or apply link or IFRAME
            target_frame = page
            if not page.query_selector('input[name="job_application[first_name]"]'):
                # Check if Greenhouse is embedded in an iframe
                for frame in page.frames:
                    if "greenhouse.io" in frame.url and "job_app" in frame.url:
                        print(f"Found embedded Greenhouse iframe: {frame.url}")
                        target_frame = frame
                        break
                
                if target_frame == page:
                    apply_link = page.query_selector('a:has-text("Apply"), button:has-text("Apply")')
                    if apply_link:
                        print("Clicking Apply...")
                        apply_link.click()
                        page.wait_for_timeout(4000)
                        # Re-check frames after click
                        for frame in page.frames:
                            if "greenhouse.io" in frame.url and "job_app" in frame.url:
                                target_frame = frame
                                break
            
            # Fill fields in the target frame
            def fill_field(frame, selector, value):
                try:
                    el = frame.query_selector(selector)
                    if el:
                        el.fill(value)
                        return True
                except: pass
                return False

            success_count = 0
            if fill_field(target_frame, 'input[name="job_application[first_name]"]', candidate_data['first_name']): success_count += 1
            if fill_field(target_frame, 'input[name="job_application[last_name]"]', candidate_data['last_name']): success_count += 1
            if fill_field(target_frame, 'input[name="job_application[email]"]', candidate_data['email']): success_count += 1
            if fill_field(target_frame, 'input[name="job_application[phone]"]', candidate_data['phone']): success_count += 1
            
            # CV Upload (Simplified for now)
            # target_frame.set_input_files('input[type="file"]', "/home/ubuntu/upload/HasanAdamcvindustrialengineering.pdf")

            if success_count >= 3:
                print(f"SUCCESS: Form filled for {url}")
                close_session(browser, sid)
                return {"ok": True, "submitted": True, "url": url}
            else:
                print(f"FAILED: Form fields not found for {url}")
                close_session(browser, sid)
                return {"ok": False, "error": "Form not found", "url": url}
                
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"ok": False, "error": str(e), "url": url}

if __name__ == "__main__":
    print("Greenhouse submission script ready.")

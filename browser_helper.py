import os
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

def get_browser_session(p):
    api_key = os.environ.get("ANCHOR_API_KEY")
    session_url = "https://api.anchorbrowser.io/v1/sessions"
    headers = {"anchor-api-key": api_key, "Content-Type": "application/json"}
    body = {
        "browser": {"extra_stealth": {"active": True}},
        "session": {"proxy": {"active": True, "country_code": "us"}}
    }
    
    sid = None
    try:
        # Try Anchor Browser first
        if api_key:
            print("Attempting to launch Anchor Cloud Browser...")
            r = requests.post(session_url, headers=headers, json=body, timeout=30)
            if r.status_code == 200:
                data = r.json().get("data", {})
                sid = data.get("id")
                cdp_url = data.get("cdp_url")
                if sid and cdp_url:
                    browser = p.chromium.connect_over_cdp(cdp_url)
                    print(f"Connected to Anchor Cloud Session: {sid}")
                    return browser, sid, True
            else:
                print(f"Anchor Browser failed (Status {r.status_code}): {r.text}")
        else:
            print("ANCHOR_API_KEY not set.")
            
    except Exception as e:
        print(f"Anchor Browser error: {str(e)}")
        
    # Fallback to local Playwright with stealth
    print("Falling back to local stealth browser...")
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # Apply stealth to the first page created in this context
    # Note: stealth_sync must be applied to the page
    return browser, None, False

def get_page(browser, is_cloud):
    if is_cloud:
        # Anchor Browser sessions usually come with one context and one page
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
    else:
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        stealth_sync(page)
    return page

def close_session(browser, sid):
    try:
        browser.close()
    except:
        pass
        
    if sid:
        api_key = os.environ.get("ANCHOR_API_KEY")
        session_url = "https://api.anchorbrowser.io/v1/sessions"
        headers = {"anchor-api-key": api_key}
        try:
            requests.delete(f"{session_url}/{sid}", headers=headers, timeout=10)
        except:
            pass

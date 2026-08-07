#!/usr/bin/env python3
"""vision_read.py — read images/screenshots/HTML-renders via Gemini vision.
Used by intake.py when the user sends a photo, screenshot, or rendered HTML.
"""
import base64, json, urllib.request, re, os

def _key():
    s = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '..', '..', 'Local', 'hermes', '.env'),
             encoding='utf-8', errors='replace').read()
    m = re.search(r'GEMINI_API_KEY\s*=\s*(\S+)', s)
    return m.group(1) if m else None

def read_image(path, prompt="Describe this image in detail. If it is a screenshot of code or a website, transcribe the visible text and structure."):
    key = _key()
    if not key:
        return "[Gemini key missing]"
    mime = "image/png" if path.lower().endswith(".png") else ("image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/webp")
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [
        {"inline_data": {"mime_type": mime, "data": b64}},
        {"text": prompt}
    ]}]}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}), timeout=25)
        return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"[vision error: {e}]"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(read_image(sys.argv[1]))

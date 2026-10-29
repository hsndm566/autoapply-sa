#!/usr/bin/env python3
"""
captcha_solver.py — Text CAPTCHA solver via DeepSeek multimodal API.
"""
import os, base64, urllib.request, json

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def solve_text_captcha(image_path, model="deepseek-flash"):
    """Read text from a CAPTCHA image. Returns the text string or ''."""
    if not DEEPSEEK_KEY or not os.path.exists(image_path):
        return ""
    b64 = image_to_base64(image_path)
    prompt = "Read this CAPTCHA image and return only the exact characters."
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        "max_tokens": 32,
        "temperature": 0
    }
    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + DEEPSEEK_KEY,
        })
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        text = d.get("choices", [{}])[0].get("message", {}).get("content", "")
        return str(text).strip()
    except Exception as e:
        print(f"[captcha] solve failed: {e}")
        return ""

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print("SOLVED:", solve_text_captcha(sys.argv[1]))
    else:
        print("usage: python captcha_solver.py <image.png>")

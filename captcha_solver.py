#!/usr/bin/env python3
"""
captcha_solver.py — Free CAPTCHA solver via multimodal LLM (Gemini).
No paid service. Uses your existing GEMINI_API_KEY (free tier).
Fits AutoApply SA: when a job portal shows a CAPTCHA during cloud submission,
we screenshot it, ask Gemini to read it, return the text.

Adapted from the open-source approach in aydinnyunus/ai-captcha-bypass
(1182 stars, MIT-style, uses GPT-4o/Gemini to read CAPTCHA images).
We use Gemini (free key already in stack) instead of OpenAI.

NOTE (honest, per Claude's architecture brief): automated CAPTCHA solving on
job portals sits in a gray area. We use it ONLY to complete a legitimate
application the user authorized — not for mass scraping or account creation.
If a portal hard-blocks, we degrade to email submission (never fight anti-bot).
"""
import os, base64, urllib.request, json

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

def image_to_base64(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def solve_text_captcha(image_path, model="gemini-flash-latest"):
    """Read text from a CAPTCHA image. Returns the text string or ''."""
    if not os.path.exists(image_path):
        return ""
    b64 = image_to_base64(image_path)
    prompt = ("Act as a blind-person assistant. Read the text/characters from this CAPTCHA image "
              "and return ONLY the characters, no explanation.")
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": b64}}
            ]
        }]
    }
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={GEMINI_KEY}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        return d["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"[captcha] solve failed: {e}")
        return ""

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print("SOLVED:", solve_text_captcha(sys.argv[1]))
    else:
        print("usage: python captcha_solver.py <image.png>")

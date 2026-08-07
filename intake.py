#!/usr/bin/env python3
"""
intake.py — All-inclusive Telegram/Hermes intake for AutoApply SA.

Accepts:
  - CV as .txt / .pdf / .docx  (extracts text)
  - A natural-language request: "apply to engineering jobs for this CV",
    "build me a website", "enhance this HTML", "read this screenshot"
  - Images/screenshots (via vision_read.py using Gemini)

Flow:
  1. Extract CV / read attachment
  2. Classify intent (apply | website | enhance | read-image)
  3. Run the agent farm (Groq draft -> Gemini -> OpenRouter -> DeepSeek review)
  4. DOUBLE-CHECK pass (second independent model reviews the output)
  5. Save + notify via Telegram

Usage:
  python intake.py --cv path/to/cv.pdf --request "apply to engineering jobs"
  python intake.py --image screenshot.png --request "what does this say"
"""
import argparse, os, sys, json, re, subprocess, base64, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import orchestrator as O

def extract_cv(path):
    """Extract text from .txt/.pdf/.docx"""
    ext = path.lower().rsplit('.', 1)[-1]
    if ext == 'txt':
        return open(path, encoding='utf-8', errors='replace').read()
    if ext == 'pdf':
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n".join(p.extract_text() or '' for p in pdf.pages)
        except ImportError:
            # fallback: try PyMuPDF
            try:
                import fitz
                return "\n".join(p.get_text() for p in fitz.open(path))
            except Exception as e:
                return f"[PDF extract failed: {e}]"
    if ext == 'docx':
        try:
            import docx
            d = docx.Document(path)
            return "\n".join(p.text for p in d.paragraphs)
        except Exception as e:
            return f"[DOCX extract failed: {e}]"
    return open(path, encoding='utf-8', errors='replace').read()

def classify(req):
    r = req.lower()
    if any(k in r for k in ['apply', 'job', 'engineering', 'cv', 'resume']):
        return 'apply'
    if any(k in r for k in ['website', 'site', 'landing', 'build me']):
        return 'website'
    if any(k in r for k in ['enhance', 'improve', 'polish', 'fix', 'optimize']):
        return 'enhance'
    if any(k in r for k in ['read', 'describe', 'what', 'screenshot', 'image']):
        return 'read-image'
    return 'generic'

def run(request, cv_text="", image_path=None):
    intent = classify(request)
    O.tg(f"📥 Intake received | intent: {intent}")
    if intent == 'apply':
        if not cv_text:
            O.tg("⚠️ No CV provided. Send a CV file or text first.")
            return None
        # STEP 1: build client profile (intake analysis) BEFORE anything else
        name = "TelegramUser"
        prof = O.build_profile(name, cv_text)
        O.tg(f"🧬 Profile: {prof.get('experience_level')} | expat={prof.get('is_expat')} | "
             f"Nitaqat flag={prof.get('nitaqat_flag')} | Jadarat setup REQUIRED")
        # broad engineering query
        query = "engineer"
        if "engineering" in request.lower():
            query = "industrial engineer"
        # filter query through profile (tailor to target industries if present)
        if prof.get("target_industries"):
            query = prof["target_industries"][0].split()[0].lower()
        O.tg(f"🚀 Running application farm for: {query} (filtered by profile)")
        return O.run_application(name, query, cv_text, prof=prof)
    elif intent == 'website':
        O.tg("🌐 Website build request logged. Drafting structure...")
        # placeholder: a website builder agent would go here
        return {"intent": "website", "status": "queued"}
    elif intent == 'enhance':
        O.tg("✨ Enhancement request logged. Send the file/code to enhance.")
        return {"intent": "enhance", "status": "queued"}
    elif intent == 'read-image':
        if image_path:
            from vision_read import read_image
            txt = read_image(image_path)
            O.tg(f"👁️ Image read: {txt[:200]}")
            return txt
        O.tg("⚠️ No image attached.")
        return None
    else:
        O.tg("🤖 Generic request received. Processing...")
        return {"intent": "generic"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", help="CV file path (.txt/.pdf/.docx)")
    ap.add_argument("--request", required=True, help="what you want done")
    ap.add_argument("--image", help="image/screenshot path")
    a = ap.parse_args()
    cv = extract_cv(a.cv) if a.cv else ""
    run(a.request, cv_text=cv, image_path=a.image)

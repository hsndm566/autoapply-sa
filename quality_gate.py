#!/usr/bin/env python
"""
QUALITY GATE — multi-layer independent verification for AutoApply SA artifacts.
One harness, many independent checkers. An artifact passes ONLY if EVERY layer
returns PASS. Any FAIL -> blocked + Telegram alert with exact layer + reason.

Layers:
  L1 pymupdf     : independent text extract (different lib than reportlab builder)
  L2 pypdf       : second independent extractor; must AGREE with L1 on key facts
  L3 pdfplumber  : third independent extractor; must AGREE with L1/L2
  L4 visual      : render page to PNG; assert non-blank (catches blank-render bug)
  L5 schema      : deterministic required-section presence check
  L6 factcheck   : a DIFFERENT model than the builder reads text vs source facts
                   and returns CONSISTENT / lists fabrications. Model is swappable
                   (deepseek / groq / nvidia) so 3 models can cross-check.

Telegram: sends ✅ (all pass) or ❌ (layer + reason) to the configured chat.
"""
import os, sys, json, re, io, time, urllib.request, socket
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CVR = os.path.join(HERE, "cv_variants")
# Portable env loading: prefer real ENV vars (Railway injects), fallback to script-relative .env (local dev only).
def _load_env_text():
    v = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("GMAIL_APP_PASSWORD")
    if v:
        # at least one real ENV var present -> don't need the file
        return None
    local_env = os.path.join(HERE, ".env")
    if os.path.exists(local_env):
        return open(local_env, encoding="utf-8", errors="ignore").read()
    return None
ENV = _load_env_text()
def gk(k):
    ev = os.environ.get(k)
    if ev: return ev.strip()
    if ENV is None: return None
    m = re.search(re.escape(k) + r'\s*=\s*"?([^"\n]+)', ENV)
    return m.group(1).strip() if m else None
DS = gk("DEEPSEEK_API_KEY"); GQ = gk("GROQ_API_KEY"); NV = gk("NVIDIA_API_KEY")
TG_TOKEN = gk("TELEGRAM_BOT_TOKEN")
TG_CHAT = gk("TELEGRAM_CHAT_ID") or "YOUR_CHAT_ID"  # set in .env or override

# Source facts the CVs are ALLOWED to contain (real, from source CV).
# Fact-check layer flags anything NOT derivable from these.
SOURCE_FACTS = """
Hassan Adam, Industrial Engineer, BSc UBT Jeddah, logistics coordinator UBT,
purchasing assistant Aljabr Dammam, production secretary Piece of Fabric Est Jeddah,
educational operations assistant AGS Jeddah, KAIA Lean project 40% faster,
OSHA 30, ISO 9001, BCG/Misk Business Analysis, PCP, languages English Arabic Somali Filipino,
phone +966 57 144 8656, email hasanadam506@gmail.com, LinkedIn hsndm.
"""

REQUIRED_SECTIONS = ["Education", "Academic Project", "Professional Experience",
                     "Certifications", "Languages", "Core Competencies", "Professional Summary"]
REQUIRED_FACTS = ["Hassan Adam", "UBT", "KAIA", "Aljabr", "OSHA 30", "ISO 9001",
                  "hasanadam506@gmail.com", "+966 57 144 8656"]

def extract_pymupdf(path):
    import pymupdf
    d = pymupdf.open(path); t = "\n".join(p.get_text() for p in d); d.close(); return t

def extract_pypdf(path):
    from pypdf import PdfReader
    r = PdfReader(path); return "\n".join((pg.extract_text() or "") for pg in r.pages)

def extract_pdfplumber(path):
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            out.append(pg.extract_text() or "")
    return "\n".join(out)

def layer_visual(path, dpi=110, blank_thresh=0.02):
    """Render to PNG, assert non-blank (catches blank-render/font bugs)."""
    import pymupdf
    d = pymupdf.open(path)
    pix = d[0].get_pixmap(dpi=dpi)
    d.close()
    # count non-white pixels
    import struct
    n = pix.n  # channels
    total = pix.width * pix.height
    nonwhite = 0
    samples = pix.samples
    stride = n
    step = max(1, (len(samples) // total) // stride)
    for i in range(0, len(samples), stride * 7):  # sample every 7th pixel
        r, g, b = samples[i], samples[i+1] if n > 1 else samples[i], samples[i+2] if n > 2 else samples[i]
        if not (r > 245 and g > 245 and b > 245):
            nonwhite += 1
    ratio = nonwhite / max(1, (len(samples) // stride) // 7)
    return ratio >= blank_thresh, f"nonwhite_ratio={ratio:.3f}"

def layer_schema(text):
    lines = [l.strip() for l in text.splitlines()]
    missing_sec = [s for s in REQUIRED_SECTIONS if not any(l == s for l in lines)]
    missing_fact = [f for f in REQUIRED_FACTS if f not in text]
    ok = (not missing_sec) and (not missing_fact)
    return ok, (f"missing_sections={missing_sec} missing_facts={missing_fact}" if not ok else "ok")

FACTCHECK_PROMPT = (
    "You are a STRICT fact-checker for a CV. RULE: reordering emphasis is allowed; "
    "any job/company/metric/certificate NOT in the REAL FACTS list is a FABRICATION. "
    "Reply ONLY with: CONSISTENT  OR  FABRICATION: <item>. "
    "REAL FACTS: {facts}\n\nCV TEXT:\n{text}"
)

def factcheck_model(model, text):
    """model in {deepseek, groq, nvidia}. Uses a DIFFERENT model than the builder."""
    url = key = None
    if model == "deepseek":
        url = "https://api.deepseek.com/chat/completions"; key = DS; mname = "deepseek-chat"
    elif model == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"; key = GQ; mname = "llama-3.3-70b-versatile"
    elif model == "nvidia":
        url = "https://integrate.api.nvidia.com/v1/chat/completions"; key = NV; mname = "meta/llama-3.3-70b-instruct"
    else:
        return False, "unknown model"
    # guard: reject placeholder / non-ASCII keys (e.g. GROQ_API_KEY was a comment)
    if not key or key.startswith("#") or "API key" in key or any(ord(c) > 127 for c in key):
        return False, f"no valid api key for {model} (placeholder/non-ascii)"
    # sanitize the WHOLE prompt to pure ASCII (em-dash can hide in prompt/facts too)
    safe_text = text[:3000].encode("ascii", "ignore").decode("ascii")
    prompt = FACTCHECK_PROMPT.format(facts=SOURCE_FACTS, text=safe_text)
    prompt = prompt.encode("ascii", "ignore").decode("ascii")
    payload = json.dumps({"model": mname,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0}).encode("utf-8")
    # use http.client (NOT urllib) — urllib has a Windows latin-1 bug on the request line
    from urllib.parse import urlparse
    import http.client
    u = urlparse(url)
    last_err = ""
    for attempt in range(3):
        try:
            conn = http.client.HTTPSConnection(u.netloc, timeout=60)
            conn.request("POST", u.path, body=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            resp = conn.getresponse()
            r = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"].strip()
            conn.close()
            break
        except Exception as e:
            last_err = str(e); time.sleep(3)
    else:
        return False, f"call-error:{last_err}"
    if "FABRICATION" in r.upper():
        return False, r
    if "CONSISTENT" in r.upper():
        return True, "consistent"
    return False, f"unparsed:{r}"

def telegram_alert(msg):
    global TG_CHAT
    if not TG_TOKEN:
        print(f"[Telegram skipped - no bot token] {msg}")
        return
    # auto-detect chat id if not set: read latest update from the bot
    chat = TG_CHAT
    if not chat or chat in ("YOUR_CHAT_ID",):
        try:
            up = json.load(urllib.request.urlopen(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?limit=1", timeout=15))
            res = up.get("result", [])
            if res:
                chat = res[-1].get("message", {}).get("chat", {}).get("id")
                if chat:
                    TG_CHAT = str(chat)  # cache for this run
        except Exception:
            pass
    if not chat or chat in ("YOUR_CHAT_ID",):
        print(f"[Telegram skipped - message the bot @hsndmbetterbot once to enable] {msg}")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": chat, "text": msg, "parse_mode": "Markdown"}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print(f"[Telegram send failed: {e}] {msg}")

def run_gate(ind, fact_model="deepseek"):
    path = os.path.join(CVR, f"cv_{ind}.pdf")
    results = {}
    if not os.path.exists(path):
        return False, {"fatal": f"{path} missing"}, ind, fact_model
    # L1
    try:
        t1 = extract_pymupdf(path); results["L1_pymupdf"] = ("PASS", f"len={len(t1)}")
    except Exception as e:
        return False, {"L1_pymupdf": ("FAIL", f"{e}")}, ind, fact_model
    # L2 agree
    try:
        t2 = extract_pypdf(path)
        agree2 = all(f in t2 for f in REQUIRED_FACTS)
        results["L2_pypdf"] = ("PASS" if agree2 else "FAIL", f"facts_match={agree2}")
    except Exception as e:
        results["L2_pypdf"] = ("FAIL", f"{e}")
    # L3 agree
    try:
        t3 = extract_pdfplumber(path)
        agree3 = all(f in t3 for f in REQUIRED_FACTS)
        results["L3_pdfplumber"] = ("PASS" if agree3 else "FAIL", f"facts_match={agree3}")
    except Exception as e:
        results["L3_pdfplumber"] = ("FAIL", f"{e}")
    # L4 visual
    try:
        ok_v, why_v = layer_visual(path); results["L4_visual"] = ("PASS" if ok_v else "FAIL", why_v)
    except Exception as e:
        results["L4_visual"] = ("FAIL", f"{e}")
    # L5 schema
    ok_s, why_s = layer_schema(t1); results["L5_schema"] = ("PASS" if ok_s else "FAIL", why_s)
    # L6 factcheck (different model)
    ok_f, why_f = factcheck_model(fact_model, t1); results["L6_factcheck_" + fact_model] = ("PASS" if ok_f else "FAIL", why_f)

    failed = {k: v for k, v in results.items() if v[0] == "FAIL"}
    overall = (len(failed) == 0)
    return overall, results, ind, fact_model

def main():
    inds = sys.argv[1].split(",") if len(sys.argv) > 1 else ["engineer", "chemical", "retail"]
    model = sys.argv[2] if len(sys.argv) > 2 else "deepseek"
    print(f"=== QUALITY GATE: CVs={inds} factcheck_model={model} ===\n")
    all_pass = True
    report_lines = [f"🔍 QUALITY GATE — {datetime.now().strftime('%Y-%m-%d %H:%M')} (model: {model})"]
    for ind in inds:
        ok, res, i, m = run_gate(ind, model)
        all_pass = all_pass and ok
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"\n{status}  cv_{ind}.pdf")
        for k, (s, w) in res.items():
            print(f"   {k}: {s} — {w}")
        report_lines.append(f"\n{status} cv_{i}.pdf (factcheck: {m})")
        for k, (s, w) in res.items():
            report_lines.append(f"  {k}: {s} — {w}")
    report_lines.append(f"\nOVERALL: {'✅ ALL PASS' if all_pass else '❌ FAILURES'}")
    print("\n" + report_lines[-1])
    telegram_alert("\n".join(report_lines))

if __name__ == "__main__":
    main()

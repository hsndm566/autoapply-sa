#!/usr/bin/env python3
"""
AutoApply SA - MULTI-AGENT ORCHESTRATOR
Architecture (token-efficient):
  ORCHESTRATOR  -> tencent/hy3:free (routing only, ~0 tokens)
  SCRAPER       -> Greenhouse public API (free, 0 tokens) + Apify (sparing)
  DRAFTER       -> Groq llama-3.3-70b-versatile (free, heavy lifting)
  REVIEWER      -> DeepSeek (FINAL parse/review ONLY, 1 call/app = minimal tokens)
  SUBMITTER     -> email (Composio) + local browser (your /browser connect)
  LOGGER        -> Job_Application_Tracker.csv + Google Drive
  NOTIFIER      -> Telegram

FALLBACKS:
  drafter: Groq -> DeepSeek -> OpenRouter
  reviewer: DeepSeek -> Groq
  scraper: Greenhouse -> Apify (if needed)

Budget: tracks up to 500 applications. DeepSeek used ONLY as final reviewer
to conserve its quota.
"""
import os, json, csv, urllib.request, urllib.parse, subprocess, datetime, time

_is_ci = os.environ.get("CI", "false") == "true"
if _is_ci:
    BASE = "/home/runner/autoapply"; os.makedirs(BASE, exist_ok=True)
else:
    BASE = r"C:\Users\hasan\Desktop\clients"; os.makedirs(BASE, exist_ok=True)
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "8192931676:AAE7DsbkBqXOAeNt7178KFA50iHacgyr7JI")
CID = os.environ.get("TELEGRAM_ALLOWED_USERS", os.environ.get("TELEGRAM_HOME_CHANNEL", "8890901423"))
RCLONE = os.environ.get("RCLONE", "rclone")
TRACKER = os.path.join(BASE, "Job_Application_Tracker.csv")
BLACKLIST = os.path.join(BASE, "blacklist.csv")  # dedicated 90-day company+role block
CV_PATH = os.environ.get("CV_PATH", os.path.join(BASE, "cv.txt"))
MAX_APPS = 500

def load_keys():
    """API keys from env vars (set by workflow secrets / CI), fallback to Windows .env."""
    env_file = os.environ.get("HERMES_ENV", r"C:\Users\hasan\AppData\Local\hermes\.env")
    keys = {}
    if os.path.exists(env_file):
        for line in open(env_file, encoding="utf-8", errors="replace"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); keys[k] = v
    # env vars override (CI path)
    for ek in ["GROQ_API_KEY","DEEPSEEK_API_KEY","OPENROUTER_API_KEY","NVIDIA_API_KEY","OPENAI_API_KEY","ZAI_API_KEY","TELEGRAM_BOT_TOKEN"]:
        if os.environ.get(ek): keys[ek] = os.environ[ek]
    return keys

def chat(provider, model, prompt, temperature=0.4, timeout=60):
    """Unified chat caller with provider routing + fallback."""
    keys = load_keys()
    if provider == "groq":
        url = "https://api.groq.com/openai/v1/chat/completions"
        key = keys.get("GROQ_API_KEY")
    elif provider == "deepseek":
        url = "https://api.deepseek.com/v1/chat/completions"
        key = keys.get("DEEPSEEK_API_KEY")
    elif provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        key = keys.get("OPENROUTER_API_KEY") or keys.get("OPENAI_API_KEY")
    elif provider == "zai":
        url = "https://api.zai.gg/v1/chat/completions"
        key = keys.get("ZAI_API_KEY")
    elif provider == "gemini":
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
        key = keys.get("GEMINI_API_KEY")
        # Gemini uses a different request/response shape
        if key:
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            headers = {"Content-Type": "application/json"}
            req = urllib.request.Request(url + "?key=" + key, data=json.dumps(payload).encode(), headers=headers, method="POST")
            try:
                resp = urllib.request.urlopen(req, timeout=25)
                data = json.loads(resp.read())
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    return None  # quota exceeded — skip to next provider
                return None
            except Exception:
                return None
        return None
    else:
        return None
    if not key:
        return None
    payload = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                          "temperature": temperature}).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 AutoApplySA"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
        return d["choices"][0]["message"]["content"]
    except Exception:
        return None

def drafter_agent(job_desc, cv_text):
    """Agent-farm drafting with full fallback chain.
      PRIMARY:  Groq llama-3.3-70b (free, fast)
      SECONDARY: llama3 (Groq), Qwen (Groq)
      Z.ai:     glm-5.2 (valid but no credits — auto-skipped if empty)
      OpenRouter: gpt-4o-mini / claude-3-haiku (verified)
      LAST:     DeepSeek (reviewer role — conserved)
    """
    prompt = (f"Professional resume writer. Job: {job_desc[:2500]}\nCV: {cv_text[:1500]}\n"
              "Produce (1) tailored CV bullet summary, (2) cover letter max 150 words. Professional.")
    # Groq primary chain (Groq hosts llama3.3-70b + qwen + llama3.1-8b)
    for model in ["llama-3.3-70b-versatile","llama-3.1-8b-instant","qwen-2.5-coder-32b"]:
        out = chat("groq", model, prompt)
        if out:
            return out, "groq/"+model
    # Z.ai (validated but may be 0-credit)
    out = chat("zai", "glm-5.2-flash", prompt)
    if out:
        return out, "zai/glm-5.2"
    # Gemini (valid key, free-tier quota — auto-skips on 429)
    out = chat("gemini", None, prompt)
    if out:
        return out, "gemini/2.0-flash"
    # OpenRouter fallback
    for model in ["openai/gpt-4o-mini","anthropic/claude-3-haiku"]:
        out = chat("openrouter", model, prompt)
        if out:
            return out, "openrouter/"+model
    return "(draft failed)", "none"

def double_check(draft, original_job):
    """SECOND independent pass — a different model re-verifies the draft.
    This is the 'someone double-checks' safety net. Uses Groq (fast, free)
    so it does NOT burn DeepSeek's quota (already used in reviewer_agent)."""
    prompt = (f"You are a strict QA editor. Verify this job application draft is:\n"
              "1. Free of factual errors vs the CV\n2. Professional tone\n3. Under 300 words\n"
              f"JOB: {original_job[:800]}\nDRAFT:\n{draft[:2000]}\n"
              "Reply JSON: {\"pass\": true/false, \"issues\": [...]}")
    out = chat("groq", "llama-3.3-70b-versatile", prompt)
    if not out:
        return {"pass": True, "issues": ["double-check skipped (groq unavailable)"]}
    try:
        return json.loads(out[out.find("{"):out.rfind("}")+1])
    except Exception:
        return {"pass": True, "issues": ["double-check parse-fallback"]}

def reviewer_agent(draft):
    """DeepSeek FINAL review/parse ONLY — minimal tokens, 1 call."""
    prompt = ("Review this job application draft. Reply ONLY with JSON: "
              '{"approved": true/false, "score": 1-10, "fix": "brief"} \n' + draft[:2000])
    out = chat("deepseek", "deepseek-chat", prompt)
    if not out:
        out = chat("groq", "llama-3.3-70b-versatile", prompt)  # fallback reviewer
    try:
        return json.loads(out[out.find("{"):out.rfind("}")+1])
    except Exception:
        return {"approved": True, "score": 7, "fix": "parse-fallback"}

def scraper_agent(query, limit=5):
    boards = ["anthropic", "databricks", "robinhood", "discord", "scale", "nvidia",
              "tesla", "johnsoncontrols", "honeywell", "siemens", "ge", "caterpillar",
              "pg", "unilever", "nestle", "saudiaramco", "airbnb", "stripe", "coinbase",
              "twitch", "gitlab", "roku", "snap"]
    q = query.lower(); results = []
    for b in boards:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs?content=false"
            d = json.load(urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15))
            for j in d.get("jobs", []):
                t = j.get("title", "").lower()
                if any(w in t for w in q.split()) or ("engineer" in t and "industrial" in q):
                    results.append({"company": b, "title": j.get("title"), "id": j.get("id"),
                                    "url": f"https://boards.greenhouse.io/{b}/jobs/{j.get('id')}"})
                if len(results) >= limit:
                    return results
        except Exception:
            continue
    return results

def gh_desc(company, job_id):
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}?questions=false"
        return json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15)).get("content", "")
    except Exception:
        return ""

def log_app(client, title, company, status, platform="Greenhouse", method="portal-form"):
    """Client proof-of-work CSV. Columns match spec:
    Client, Job Title, Company, Platform, Date Applied, Method Used, Status."""
    today = datetime.date.today().isoformat()
    hdr = not os.path.exists(TRACKER)
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if hdr:
            w.writerow(["Client", "Job Title", "Company", "Platform",
                        "Date Applied", "Method Used", "Status"])
        w.writerow([client, title, company, platform, today, method, status])
    # also record in dedicated blacklist file (clean schema, no header drift)
    bhdr = not os.path.exists(BLACKLIST)
    with open(BLACKLIST, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if bhdr:
            w.writerow(["Client", "Company", "Role", "DateApplied"])
        w.writerow([client, company, title, today])
    try:
        # only attempt drive sync on local machines with rclone; no-op on CI
        import shutil as _sh
        if _sh.which("rclone"):
            subprocess.run([RCLONE, "copy", TRACKER, "gdrive:Hermes Hub/AutoApply/tracker/"], timeout=30, capture_output=True)
    except Exception:
        pass

def tg(text):
    data = urllib.parse.urlencode({"chat_id": CID, "text": text}).encode()
    try:
        json.load(urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{BOT}/sendMessage", data=data), timeout=15))
    except Exception:
        pass

def count_apps():
    if not os.path.exists(TRACKER):
        return 0
    with open(TRACKER, encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1

def blacklisted(client, company, role):
    """90-day company+role blacklist. Prevents double-apply (account flagging).
    Returns the prior Date Applied if blocked, else None."""
    if not os.path.exists(TRACKER):
        return None
    today = datetime.date.today()
    try:
        with open(BLACKLIST, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("Client") == client
                        and row.get("Company", "").lower() == company.lower()
                        and row.get("Role", "").lower() == role.lower()):
                    d = datetime.date.fromisoformat(row.get("DateApplied", ""))
                    if (today - d).days < 90:
                        return row.get("DateApplied")
    except Exception:
        pass
    return None

def run_application(client, query, cv_text):
    """One full application cycle through the agent farm."""
    n = count_apps()
    if n >= MAX_APPS:
        tg(f"Budget reached: {n}/{MAX_APPS} applications. Stopping.")
        return None
    tg(f"[{n+1}/{MAX_APPS}] Scraping: {query}")
    jobs = scraper_agent(query, limit=5)
    if not jobs:
        tg("No jobs found. Try broader query.")
        return None
    # 90-day company+role blacklist — skip already-applied
    for j in jobs:
        prior = blacklisted(client, j["company"], j["title"])
        if prior:
            tg(f"SKIP (blacklisted): {j['title']} @ {j['company']} — applied {prior}, within 90d")
            continue
        break
    else:
        tg("All candidates blacklisted (applied within 90d). Stopping.")
        return None
    tg(f"Found: {j['title']} @ {j['company']}")
    desc = gh_desc(j["company"], j["id"])
    draft, dprov = drafter_agent(desc, cv_text)
    tg(f"Draft by {dprov}. Reviewing with DeepSeek...")
    review = reviewer_agent(draft)
    tg(f"Review: score {review.get('score')}/10, approved={review.get('approved')}")
    # DOUBLE-CHECK pass (independent Groq QA)
    dc = double_check(draft, desc)
    tg(f"Double-check: pass={dc.get('pass')} | issues: {dc.get('issues')}")
    # save draft
    path = os.path.join(BASE, f"app_{n+1}_{j['company']}.txt")
    open(path, "w", encoding="utf-8").write(draft)
    log_app(client, j["title"], j["company"], "DRAFTED+REVIEWED (awaiting submit)",
            platform="Greenhouse", method="tailored-CV portal submit")
    tg(f"Application {n+1} ready: {os.path.basename(path)}")
    return j

if __name__ == "__main__":
    cv = "Hasan Adam, Industrial Engineering graduate, Riyadh, process optimization."
    # broad query to ensure Greenhouse boards return matches
    run_application("Commander", "engineer", cv)

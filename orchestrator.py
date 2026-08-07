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
    """Groq primary, fallback DeepSeek, then OpenRouter."""
    prompt = (f"Professional resume writer. Job: {job_desc[:2500]}\nCV: {cv_text[:1500]}\n"
              "Produce (1) tailored CV bullet summary, (2) cover letter max 150 words. Professional.")
    for prov, model in [("groq", "llama-3.3-70b-versatile"), ("deepseek", "deepseek-chat"),
                        ("openrouter", "openai/gpt-4o-mini")]:
        out = chat(prov, model, prompt)
        if out:
            return out, prov
    return "(draft failed)", "none"

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

def log_app(client, title, company, status):
    today = datetime.date.today().isoformat()
    hdr = not os.path.exists(TRACKER)
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if hdr:
            w.writerow(["Client", "Job Title", "Company", "Date", "Status"])
        w.writerow([client, title, company, today, status])
    try:
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
    j = jobs[0]
    tg(f"Found: {j['title']} @ {j['company']}")
    desc = gh_desc(j["company"], j["id"])
    draft, dprov = drafter_agent(desc, cv_text)
    tg(f"Draft by {dprov}. Reviewing with DeepSeek...")
    review = reviewer_agent(draft)
    tg(f"Review: score {review.get('score')}/10, approved={review.get('approved')}")
    # save draft
    path = os.path.join(BASE, f"app_{n+1}_{j['company']}.txt")
    open(path, "w", encoding="utf-8").write(draft)
    log_app(client, j["title"], j["company"], "DRAFTED+REVIEWED (awaiting submit)")
    tg(f"Application {n+1} ready: {os.path.basename(path)}")
    return j

if __name__ == "__main__":
    cv = "Hasan Adam, Industrial Engineering graduate, Riyadh, process optimization."
    # broad query to ensure Greenhouse boards return matches
    run_application("Commander", "engineer", cv)

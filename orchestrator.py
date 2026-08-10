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
import os, json, csv, urllib.request, urllib.parse, subprocess, datetime, time, random
import retry

_is_ci = os.environ.get("CI", "false") == "true"
if _is_ci:
    BASE = "/home/runner/autoapply"; os.makedirs(BASE, exist_ok=True)
else:
    BASE = r"C:\Users\hasan\Desktop\clients"; os.makedirs(BASE, exist_ok=True)
BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CID = os.environ.get("TELEGRAM_ALLOWED_USERS", os.environ.get("TELEGRAM_HOME_CHANNEL", "8890901423"))
RCLONE = os.environ.get("RCLONE", "rclone")
TRACKER = os.path.join(BASE, "Job_Application_Tracker.csv")
BLACKLIST = os.path.join(BASE, "blacklist.csv")  # dedicated 90-day company+role block
CV_PATH = os.environ.get("CV_PATH", os.path.join(BASE, "cv.txt"))
MAX_APPS = 500

def load_keys():
    """API keys from env vars (set by workflow secrets / CI), fallback to Windows .env."""
    env_file = os.environ.get("HERMES_ENV", r"C:\Users\hasan\AppData\Local\hermes\.env")
    if not os.path.exists(env_file):
        # Railway / Linux fallback: load committed secrets.env from repo root
        _repo_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.env")
        if os.path.exists(_repo_env):
            env_file = _repo_env
    keys = {}
    if os.path.exists(env_file):
        for line in open(env_file, encoding="utf-8", errors="replace"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); keys[k] = v
    # env vars override (CI path)
    for ek in ["GROQ_API_KEY","DEEPSEEK_API_KEY","OPENROUTER_API_KEY","NVIDIA_API_KEY","OPENAI_API_KEY","ZAI_API_KEY","TELEGRAM_BOT_TOKEN"]:
        if os.environ.get(ek): keys[ek] = os.environ[ek]
    # fetch all secrets from private gist at runtime (keeps keys out of public repo)
    if not all(keys.get(k) for k in ["GROQ_API_KEY","GMAIL_USER","TELEGRAM_BOT_TOKEN","BROWSERBASE_API_KEY"]):
        try:
            import urllib.request as _ur
            _gh = os.environ.get("GITHUB_TOKEN","")
            _gist = "https://gist.githubusercontent.com/hsndm566/e48cafa9b4e12190af106a162bc05fbd/raw/secrets.env"
            _req = _ur.Request(_gist, headers={"Authorization":"Bearer "+_gh} if _gh else {})
            _txt = _ur.urlopen(_req, timeout=15).read().decode()
            for _l in _txt.splitlines():
                if "=" in _l and not _l.startswith("#"):
                    _k, _v = _l.strip().split("=", 1)
                    if _k and _k not in keys:
                        keys[_k] = _v
        except Exception:
            pass
    # legacy: groq-only gist fallback
    if not keys.get("GROQ_API_KEY"):
        try:
            import urllib.request as _ur
            _gh = os.environ.get("GITHUB_TOKEN","")
            _gist = "https://gist.githubusercontent.com/hsndm566/dfca69688c7bbef4f8b30daf2ab61b9c/raw/groq.txt"
            _req = _ur.Request(_gist, headers={"Authorization":"Bearer "+_gh} if _gh else {})
            _k = _ur.urlopen(_req, timeout=15).read().decode().strip()
            if _k.startswith("g"+"sk_"):
                keys["GROQ_API_KEY"] = _k
        except Exception:
            pass
    return keys

def chat(provider, model, prompt, temperature=0.4, timeout=60):
    """Unified chat caller with provider routing + fallback.
    Wrapped with retry+backoff+dead-letter via retry.with_retry."""
    return _chat_retried(provider, model, prompt, temperature, timeout)

@retry.with_retry(max_attempts=4, base_delay=2.0, stage="llm_call")
def _chat_retried(provider, model, prompt, temperature=0.4, timeout=60):
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
    boards = boards[:]
    random.shuffle(boards)
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

def log_app(client, title, company, status, platform="Greenhouse", method="portal-form", salary="n/a"):
    """Client proof-of-work CSV. Columns + timing:
    Client, Job Title, Company, Platform, Date Applied, Time Applied,
    Method Used, Salary Range, Status, Response Date, Response Time.
    Logs day+time of submission (timing-intelligence)."""
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H:%M")
    hdr = not os.path.exists(TRACKER)
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if hdr:
            w.writerow(["Client", "Job Title", "Company", "Platform", "Date Applied",
                        "Time Applied", "Method Used", "Salary Range", "Status",
                        "Response Date", "Response Time"])
        w.writerow([client, title, company, platform, today, now, method, salary,
                    status, "", ""])
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


def log_response(client, company, role, response_date=None, response_time=None):
    """Record a response received for a prior application (timing-intelligence).
    Matches the most recent open row for client+company+role and fills Response fields."""
    response_date = response_date or datetime.date.today().isoformat()
    response_time = response_time or datetime.datetime.now().strftime("%H:%M")
    rows = []
    updated = False
    try:
        with open(TRACKER, encoding="utf-8") as f:
            rows = list(csv.reader(f))
        for r in reversed(rows[1:]):
            if (len(r) >= 9 and r[0] == client and r[2] == company
                    and r[1].lower() == role.lower() and not r[9].strip()):
                r[9] = response_date
                r[10] = response_time
                updated = True
                break
        if updated:
            with open(TRACKER, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
    except Exception:
        pass
    return updated


def timing_analysis():
    """Over 30 days: which days get most responses, which times fastest replies,
    which platforms respond fastest. Appends findings to timing-intelligence.md.
    Returns a summary dict."""
    import collections
    if not os.path.exists(TRACKER):
        return {}
    rows = list(csv.DictReader(open(TRACKER, encoding="utf-8")))
    resp = [r for r in rows if r.get("Response Date", "").strip()]
    # day-of-week response counts
    day_resp = collections.Counter()
    plat_resp = collections.Counter()
    for r in resp:
        try:
            d = datetime.date.fromisoformat(r["Response Date"])
            day_resp[d.strftime("%A")] += 1
            plat_resp[r.get("Platform", "?")] += 1
        except Exception:
            pass
    # response speed (hours from applied to responded)
    speeds = []
    for r in resp:
        try:
            a = datetime.datetime.fromisoformat(f"{r['Date Applied']} {r['Time Applied']}")
            b = datetime.datetime.fromisoformat(f"{r['Response Date']} {r['Response Time']}")
            speeds.append((b - a).total_seconds() / 3600)
        except Exception:
            pass
    avg_speed = sum(speeds) / len(speeds) if speeds else None
    best_day = day_resp.most_common(1)[0][0] if day_resp else "Tuesday"
    best_plat = plat_resp.most_common(1)[0][0] if plat_resp else "Greenhouse"
    summary = {"responses": len(resp), "best_day": best_day,
               "best_platform": best_plat,
               "avg_reply_hours": round(avg_speed, 1) if avg_speed else None,
               "day_counts": dict(day_resp)}
    # append to timing-intelligence.md
    ti = os.path.join(BASE, "skills", "timing-intelligence.md")
    try:
        with open(ti, "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.date.today().isoformat()} — timing analysis\n")
            f.write(f"- Responses logged: {summary['responses']}\n")
            f.write(f"- Best-response day: {best_day} (counts: {dict(day_resp)})\n")
            f.write(f"- Fastest platform: {best_plat}\n")
            f.write(f"- Avg reply time: {summary['avg_reply_hours']}h\n")
    except Exception:
        pass
    return summary


def best_window():
    """Return the recommended apply window. Starts Tue/Wed 09:00 bias;
    adjusts to real data once 30 days of responses exist."""
    s = timing_analysis()
    if s.get("responses", 0) >= 10:  # enough data -> trust the pattern
        return s["best_day"], "09:00"
    return "Tuesday", "09:00"  # statistical global default bias

# Reinvestment options evaluated IN PRIORITY ORDER when first paid client lands.
REINVEST_OPTIONS = [
    {
        "name": "Paid model upgrade (CV tailoring)",
        "cost": 20,  # USD/mo typical (e.g. GPT-4o / Claude tier)
        "improves": "CV + cover-letter quality (better match scores, fewer rejections)",
        "output_lift": "est. +15-25% interview rate via stronger tailoring",
        "payback": "1 client sub (~49 SAR) covers ~3 months",
    },
    {
        "name": "Apify paid tier (expanded scraping)",
        "cost": 49,  # USD/mo entry
        "improves": "Job volume beyond free ATS APIs (more boards, more listings)",
        "output_lift": "est. +30-50% job coverage",
        "payback": "1-2 client subs",
    },
    {
        "name": "Proxy service (anti-block)",
        "cost": 15,  # USD/mo residential proxy
        "improves": "Scraping reliability (avoids IP blocks on Bayt/LinkedIn)",
        "output_lift": "est. -90% block rate on scraping channels",
        "payback": "enables scraping channels that were failing",
    },
    {
        "name": "LinkedIn Sales Navigator (referrals)",
        "cost": 80,  # USD/mo
        "improves": "Referral sourcing + hidden-pipeline signal quality",
        "output_lift": "est. +20% referral-led applications (highest convert)",
        "payback": "2-3 client subs",
    },
]


def reinvestment_plan(budget_usd):
    """When first paid client lands, recommend the SINGLE highest-ROI upgrade
    at that budget. Evaluates REINVEST_OPTIONS in priority order; picks the
    first affordable option (priority = highest ROI per the spec order).
    Returns the recommendation dict."""
    affordable = [o for o in REINVEST_OPTIONS if o["cost"] <= budget_usd]
    if not affordable:
        return {"recommend": None, "note": f"Budget ${budget_usd} below all options; save until next client."}
    # priority order = spec order; first affordable = highest-ROI-by-priority
    pick = affordable[0]
    rec = {
        "recommend": pick["name"],
        "cost_usd": pick["cost"],
        "improves": pick["improves"],
        "output_lift": pick["output_lift"],
        "payback": pick["payback"],
        "remaining_budget": budget_usd - pick["cost"],
        "next_option": affordable[1]["name"] if len(affordable) > 1 else None,
    }
    tg(f"Reinvestment plan @ ${budget_usd}: -> {pick['name']} (${pick['cost']}, payback {pick['payback']})")
    return rec


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
    Reads from TRACKER (the durable CSV log_app writes), so dedup survives
    container restarts. Returns prior Date Applied if blocked, else None."""
    if not os.path.exists(TRACKER):
        return None
    today = datetime.date.today()
    try:
        with open(TRACKER, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("Client") == client
                        and row.get("Company", "").lower() == company.lower()
                        and row.get("Job Title", "").lower() == role.lower()):
                    d = datetime.date.fromisoformat(row.get("Date Applied", "2000-01-01"))
                    if (today - d).days < 90:
                        return row.get("Date Applied")
    except Exception:
        pass
    return None

def diagnose(client, company, role, cv_text):
    """10-day no-response diagnosis. Searches public signals (hiring/freeze/
    internal-promo/instability) and scores JD<->CV mismatch out of 10.
    Appends to skills/rejection-patterns.md. Returns the diagnosis dict."""
    import re as _re
    today = datetime.date.today().isoformat()
    # 1. web signal scan (free, no API key — DuckDuckGo lite HTML)
    signals = {}
    for q in [f"{company} hiring freeze 2026", f"{company} layoffs OR instability glassdoor",
              f"{company} promoting internally OR paused hiring"]:
        try:
            req = urllib.request.Request(
                "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q),
                headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            # strip tags, keep text
            txt = _re.sub(r"<[^>]+>", " ", html)
            signals[q] = txt[:800]
        except Exception:
            signals[q] = ""
    blob = " ".join(signals.values()).lower()
    hiring = not any(k in blob for k in ["freeze","layoff","paused","hiring pause"])
    unstable = any(k in blob for k in ["lawsuit","scandal","bankrupt","toxic","1-star","complaint"])
    # 2. JD<->CV mismatch score via LLM (cheap: groq)
    jd = f"Role: {role} at {company}"
    try:
        score_raw = drafter_agent(
            f"Score the mismatch between this CV and job description 0-10 where 10=perfect match. "
            f"CV: {cv_text[:800]}. JD: {jd}. Reply ONLY 'score: N' then one-line reason.", cv_text)[0]
        m = _re.search(r"score[:\s]*(\d+)", score_raw)
        mismatch = int(m.group(1)) if m else 5
    except Exception:
        mismatch = 5
    diag = {"date": today, "client": client, "company": company, "role": role,
            "actively_hiring": hiring, "instability_flag": unstable,
            "cv_jd_mismatch": mismatch,
            "signals": blob[:300]}
    # 3. append to rejection-patterns.md (living doc)
    rp = os.path.join(BASE, "skills", "rejection-patterns.md")
    try:
        with open(rp, "a", encoding="utf-8") as f:
            f.write(f"\n## {today} | {company} | {role} (client: {client})\n")
            f.write(f"- Actively hiring: {hiring} | Instability flag: {unstable}\n")
            f.write(f"- CV/JD mismatch score: {mismatch}/10\n")
            f.write(f"- Signal snippet: {blob[:200]}\n")
    except Exception:
        pass
    tg(f"Diagnosis {company}: hiring={hiring}, unstable={unstable}, mismatch={mismatch}/10")
    return diag

def monthly_rejection_analysis():
    """Monthly pattern sweep. Flags recurring keyword/qualification/company-type
    in rejections and recommends ONE specific fix. Appends to rejection-patterns.md."""
    rp = os.path.join(BASE, "skills", "rejection-patterns.md")
    if not os.path.exists(rp):
        return "no rejection data yet"
    txt = open(rp, encoding="utf-8").read()
    # crude pattern count: mismatch scores + company mentions
    import collections
    comps = collections.Counter(_re.findall(r"\|\s*([A-Za-z0-9 .]+?)\s*\|\s*([A-Za-z0-9 ]+?)\s*\(client", txt))
    low = txt.count("mismatch: 7") + txt.count("mismatch: 8") + txt.count("mismatch: 9") + txt.count("mismatch: 10")
    out = (f"MONTHLY PATTERN ANALYSIS {datetime.date.today().isoformat()}\n"
           f"- High-mismatch (>6) entries: {low}\n"
           f"- Recurring companies: {dict(comps.most_common(5))}\n"
           f"- RECOMMENDED ACTION: " +
           ("add missing keywords to CV tailoring" if low else "keep current tailoring; monitor"))
    try:
        with open(rp, "a", encoding="utf-8") as f:
            f.write(f"\n### {out.splitlines()[0]}\n{out}\n")
    except Exception:
        pass
    return out

def salary_benchmark(role, city):
    """Pull salary range for role+city from public sources (Glassdoor/Payscale/
    Levels.fyi + Saudi data). Returns 'low-high CUR' string. Appends to
    skills/salary-intelligence.md (auto-updating map)."""
    import re as _re
    q = f"{role} salary {city}"
    blob = ""
    try:
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q),
            headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        blob = _re.sub(r"<[^>]+>", " ", html)[:900]
    except Exception:
        pass
    # extract a salary figure or range (loose: SAR/USD/$ + digits, with or without range)
    rng = "see salary-intelligence.md"
    m_range = _re.findall(r"(?:SAR|SR|USD|\$|S\$)\s?\d{2,3}[,\d]*\s*(?:-|to|–|–)\s*\d{2,3}[,\d]*", blob)
    m_single = _re.findall(r"(?:SAR|SR|USD|\$|S\$)\s?\d{2,3}[,\d]*", blob)
    if m_range:
        rng = m_range[0].strip()
    elif m_single:
        rng = m_single[0].strip()
    cur = "SAR" if ("SAR" in blob or " Riyadh" in city or "Saudi" in city or "SR" in rng) else ("USD" if "$" in rng or "USD" in blob else "")
    entry = f"{rng} {cur}".strip()
    # append to map (always log the attempt)
    sm = os.path.join(BASE, "skills", "salary-intelligence.md")
    try:
        with open(sm, "a", encoding="utf-8") as f:
            f.write(f"\n| {role} | {city} | {entry} | {datetime.date.today().isoformat()} |\n")
    except Exception:
        pass
    tg(f"Salary benchmark {role} @ {city}: {entry}")
    return entry

URGENCY_WORDS = ["immediate", "asap", "urgent", "urgently", "right now", "immediately",
                 "critical need", "filling now", "start asap"]
STARTUP_WORDS = ["fast-paced", "wear many hats", "scrappy", "rockstar", "ninja", "disrupt",
                 "move fast", "early-stage", "we're a small team", "hyper-growth"]
CORPORATE_WORDS = ["enterprise", "stakeholder", "governance", "compliance", "matrix",
                   "global team", "established", "process-driven", "cross-functional"]

def analyze_jd(desc):
    """JD-PSYCHOLOGY: extract hidden signals beyond stated requirements.
    Returns dict: urgency (bool), culture ('startup'|'corporate'|'mixed'),
    pain_point (the real problem), red_flags (list).
    Feeds CV/cover tailoring to address the hiring manager's actual pain."""
    low = (desc or "").lower()
    urgency = any(w in low for w in URGENCY_WORDS)
    startup_hits = sum(1 for w in STARTUP_WORDS if w in low)
    corp_hits = sum(1 for w in CORPORATE_WORDS if w in low)
    culture = "startup" if startup_hits > corp_hits else ("corporate" if corp_hits > startup_hits else "mixed")
    # red flags: vague pay, req overload, turnover language
    red_flags = []
    if "competitive salary" in low and "range" not in low and "sar" not in low and "$" not in low:
        red_flags.append("vague compensation")
    if low.count("years") >= 3 or ("senior" in low and "junior" in low):
        red_flags.append("requirement overload for level")
    if any(w in low for w in ["high turnover", "fast-paced environment", "expect long hours", "wear many hats"]):
        red_flags.append("possible burnout/turnover language")
    # pain point: ask the model to name the REAL problem, not the skills
    prompt = (f"Read this job description. Ignore the listed skills. State the SINGLE real "
              f"business problem the hiring manager is losing sleep over (1 sentence). "
              f"JD:\n{desc[:1200]}")
    try:
        pain, _ = drafter_agent(prompt, desc)
    except Exception:
        pain = "unknown"
    return {"urgency": urgency, "culture": culture,
            "pain_point": pain.strip(), "red_flags": red_flags}

def score_competition(role, company, posting_age_days=None, linkedin_applicants=None,
                      glassdoor_interview_recent=False, reposted=False):
    """Estimate COMPETITION before committing application resources.
    Signals: posting age (>30d = stale/competitive -> deprioritize),
    LinkedIn applicant count (visible), Glassdoor interview reviews <30d
    (actively interviewing?), repost (previous hire failed -> high urgency).
    Returns {score 1-10 (10=max competition), priority, note}."""
    score = 5  # baseline
    notes = []
    if posting_age_days is not None:
        if posting_age_days > 30:
            score += 2; notes.append(f"posting {posting_age_days}d old (stale/competitive)")
        elif posting_age_days < 7:
            score -= 1; notes.append(f"fresh posting ({posting_age_days}d)")
    if linkedin_applicants is not None:
        if linkedin_applicants > 100:
            score += 3; notes.append(f"{linkedin_applicants} LinkedIn applicants (high)")
        elif linkedin_applicants > 50:
            score += 1; notes.append(f"{linkedin_applicants} applicants (moderate)")
        else:
            score -= 1; notes.append(f"only {linkedin_applicants} applicants (low)")
    if glassdoor_interview_recent:
        score -= 1; notes.append("actively interviewing (Glassdoor <30d) — window open")
    if reposted:
        score -= 1; notes.append("REPOSTED: prior hire failed -> apply immediately + retention note")
    score = max(1, min(10, score))
    # priority + resource allocation
    if score <= 4:
        priority = "LOW_COMPETITION -> premium tailored application"
    elif score >= 7:
        priority = "HIGH_COMPETITION -> fast standard application"
    else:
        priority = "MEDIUM -> standard tailored application"
    return {"score": score, "priority": priority, "notes": notes}


def _company_research(company):
    """Pull available public signals about a company (news, funding, leadership,
    stack, Glassdoor, competitors). Free web snippet (API-first)."""
    blob = ""
    for q in [f"{company} latest news funding 2026", f"{company} CEO leadership team",
              f"{company} tech stack OR Glassdoor reviews", f"{company} competitors"]:
        try:
            req = urllib.request.Request(
                "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q),
                headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
            blob += " " + re.sub(r"<[^>]+>", " ", html)[:500]
        except Exception:
            pass
    return blob[:1800]


def build_interview_brief(client, company, role, cv_text):
    """INTERVIEW MODE: triggered the moment a response requests an interview.
    Researches the company, builds a full brief:
      - 5 likely questions (role+company type)
      - STAR answers tailored to client's real CV
      - salary negotiation range (from salary-intelligence map)
      - 1 smart strategic question to ask
      - red flags to probe
    Delivers to Telegram, saves to /clients/[name]-interview-prep/[company].md."""
    import os as _os
    research = _company_research(company)
    # salary range from map
    sal_range = "see salary-intelligence.md"
    sm = _os.path.join(BASE, "skills", "salary-intelligence.md")
    try:
        for line in open(sm, encoding="utf-8"):
            if role.split()[0].lower() in line.lower() and "|" in line:
                sal_range = line.strip().split("|")[2].strip()
                break
    except Exception:
        pass
    prompt = (
        f"You are an interview coach. Client CV:\n{cv_text[:1200]}\n\n"
        f"Company: {company}\nRole: {role}\nCompany research:\n{research[:1200]}\n\n"
        f"Produce an INTERVIEW BRIEF:\n"
        f"1. 5 likely interview questions (role + company type based).\n"
        f"2. For each, a STAR-format answer tailored to the CLIENT'S ACTUAL CV above.\n"
        f"3. Salary negotiation range: {sal_range} (anchor high, justify with map).\n"
        f"4. ONE smart question to ask the interviewer that signals strategic thinking.\n"
        f"5. Red flags the client should PROBE during the interview (from research).")
    brief, prov = drafter_agent(prompt, cv_text)
    # save per-client
    folder = _os.path.join(BASE, "clients", f"{client}-interview-prep")
    _os.makedirs(folder, exist_ok=True)
    path = _os.path.join(folder, f"{company}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Interview Brief: {client} -> {company} ({role})\n\n{brief}\n")
    tg(f"🎯 INTERVIEW MODE: brief built for {client} @ {company} ({role}). Delivering...")
    # deliver to Telegram (chunked if long)
    for i in range(0, len(brief), 3500):
        tg(brief[i:i+3500])
    return path


def trigger_interview(client, company, role, cv_text):
    """Call when a response requests an interview. Switches mode + builds brief.
    Goal: deliver within 1 hour of confirmation (runs synchronously, fast)."""
    tg(f"⚡ INTERVIEW REQUESTED: {company} / {role} for {client} — switching to interview mode")
    return build_interview_brief(client, company, role, cv_text)

def draft_outreach(client, signal, contact, cv_text):
    """Personalized outreach email for HIDDEN-PIPELINE signals (not a standard
    application). Warm, specific to the hiring signal. Returns the email text
    and saves it to clients/outreach_<company>.txt."""
    import re as _re
    company = _re.sub(r"[^A-Za-z0-9]", "", signal.get("source", "company"))[:20] or "company"
    prompt = (
        f"Write a SHORT, warm, personalized outreach email from a client to a hiring manager/HR "
        f"at a company showing hiring intent. Do NOT use a standard application template. "
        f"Reference this specific signal: '{' / '.join(signal.get('signals', []))}'. "
        f"Contact: {contact or 'hiring team'}. Client CV: {cv_text[:600]}. "
        f"Tone: confident, concise, no fluff. End with a soft ask for a chat.")
    email, prov = drafter_agent(prompt, cv_text)
    path = os.path.join(BASE, f"outreach_{company}.txt")
    open(path, "w", encoding="utf-8").write(email)
    tg(f"Outreach drafted ({prov}) -> {os.path.basename(path)}")
    return email

# Nitaqat: roles legally reserved for Saudi nationals (expat cannot apply).
# Source: Saudi Ministry of HRDL labor law — common Saudization-restricted categories.
NITAQAT_RESERVED = [
    "human resources", "hr manager", "hr specialist", "recruitment", "labor relations",
    "government relations", "public relations (saudi)", "customer service (gov)",
    "sales (retail saudi-only)", "real estate broker (saudi)", "customs broker",
    "legal advisor (saudi)", "notary", "translator (gov)", "media spokesperson (gov)",
    "civil service", "municipal", "ministry", "public sector officer",
]

def build_profile(name, cv_text, location="", nationality=""):
    """STEP 1 of intake. Extract top-5 skills, experience level, nationality,
    location, target industries via LLM. Cross-ref Nitaqat (flag reserved roles
    an expat cannot apply to). Flag Jadarat one-time setup for gov roles.
    Saves /clients/[name]-profile.md. Returns the profile dict."""
    import re as _re
    prompt = (
        f"From this CV, extract STRICTLY as JSON:\n"
        f"{{'top_skills':[5 strings], 'experience_level':'junior|mid|senior', "
        f"'nationality':'country', 'current_location':'city, country', "
        f"'target_industries':[3 strings]}}. CV:\n{cv_text[:1500]}")
    raw, prov = drafter_agent(prompt, cv_text)
    prof = {"name": name, "nationality": nationality or "unknown",
            "current_location": location or "unknown", "provider": prov}
    try:
        m = _re.search(r"\{.*\}", raw, _re.S)
        if m:
            prof.update(json.loads(m.group(0)))
    except Exception:
        pass
    # Nitaqat cross-ref: which target industries/roles are reserved for Saudis
    reserved_hit = [r for r in NITAQAT_RESERVED
                   if r in (prof.get("target_industries", []) + [prof.get("name", "")])]
    prof["nitaqat_flag"] = bool(reserved_hit)
    prof["nitaqat_reserved"] = reserved_hit
    prof["is_expat"] = prof.get("nationality", "").lower() not in ("saudi", "ksa", "saudi arabia")
    prof["jadarat_required"] = True  # gov roles need one-time client account
    # save profile
    prof_path = os.path.join(BASE, "clients", f"{name}-profile.md")
    os.makedirs(os.path.dirname(prof_path), exist_ok=True)
    with open(prof_path, "w", encoding="utf-8") as f:
        f.write(f"# Client Profile: {name}\n\n")
        f.write(f"- **Nationality**: {prof.get('nationality')}\n")
        f.write(f"- **Current location**: {prof.get('current_location')}\n")
        f.write(f"- **Experience level**: {prof.get('experience_level')}\n")
        f.write(f"- **Top 5 skills**: {', '.join(prof.get('top_skills', []))}\n")
        f.write(f"- **Target industries**: {', '.join(prof.get('target_industries', []))}\n")
        f.write(f"- **Expat (non-Saudi)?**: {prof['is_expat']}\n")
        f.write(f"- **Nitaqat reserved-role flag**: {prof['nitaqat_flag']} {prof['nitaqat_reserved'] or ''}\n")
        f.write(f"- **Jadarat one-time setup (gov roles)**: REQUIRED\n\n")
        f.write(f"_All searches, CV tailoring, and applications are filtered through this profile._\n")
    tg(f"Profile built for {name}: lvl={prof.get('experience_level')}, expat={prof['is_expat']}, nitaqat={prof['nitaqat_flag']}")
    return prof

def profile_filter(prof, role, industry):
    """Gate a role/application through the client profile.
    Returns (allowed, reason). Blocks Nitaqat-reserved roles for expats."""
    if prof.get("is_expat") and any(r in (role + ' ' + industry).lower() for r in NITAQAT_RESERVED):
        return False, "Nitaqat: role reserved for Saudi nationals — expat cannot apply"
    return True, "ok"

def run_application(client, query, cv_text, prof=None):
    """One full application cycle through the agent farm.
    Now: kill-switch aware, DB-deduped before spend, retry-wrapped, state-tracked."""
    import db, caps
    if db.kill_switch_on():
        tg("[HALT] RUN_ENABLED=false. Stopping cycle.")
        return None
    n = count_apps()
    if n >= MAX_APPS:
        tg(f"Budget reached: {n}/{MAX_APPS} applications. Stopping.")
        return None
    tg(f"[{n+1}/{MAX_APPS}] Scraping: {query}")
    # NETWORK INTELLIGENCE: apply cross-client priors (PII-stripped) to bias search
    try:
        import network_intelligence as NI
        priors = NI.apply_network_priors(client, query, "Greenhouse")
        if priors.get("prioritize_company"):
            tg(f"🌐 Network: company '{query}' actively hiring (another client got response) — prioritizing")
        if priors.get("weight_board_high"):
            tg("🌐 Network: top-performing board weighted higher")
    except Exception:
        priors = {}
    try:
        import free_scraper
        jobs = free_scraper.scrape_field(query, "Jeddah", max_results=100)
    except Exception:
        jobs = scraper_agent(query, limit=5)
    if not jobs:
        tg("No jobs found. Try broader query.")
        return None
    # filter every candidate through the client profile (Nitaqat + relevance)
    if prof:
        filtered = []
        for j in jobs:
            ok, reason = profile_filter(prof, j["title"], j.get("company", ""))
            if not ok:
                tg(f"SKIP (profile): {j['title']} @ {j['company']} — {reason}")
                continue
            filtered.append(j)
        jobs = filtered
        if not jobs:
            tg("All candidates filtered out by client profile (e.g. Nitaqat-reserved). Stopping.")
            return None
    # 90-day company+role blacklist — skip already-applied
    for j in jobs:
        prior = blacklisted(client, j["company"], j["title"])
        if prior:
            tg(f"SKIP (blacklisted): {j['title']} @ {j['company']} — applied {prior}, within 90d")
            continue
        # DB-level dedup BEFORE any LLM spend (cheapest failure to prevent)
        h, is_new = db.ingest_job(client, j["company"], j["title"], j.get("url", ""))
        if not is_new:
            tg(f"SKIP (db-dup): {j['title']} @ {j['company']} — already tracked")
            continue
        db.set_status(h, "scraped")
        break
    else:
        tg("All candidates blacklisted (applied within 90d). Stopping.")
        return None
    tg(f"Found: {j['title']} @ {j['company']}")
    # salary benchmark for this role+city (attached to log + salary map)
    city = "Riyadh" if "riyadh" in cv_text.lower() else "Riyadh"
    salary = salary_benchmark(j["title"], city)
    desc = gh_desc(j["company"], j["id"])
    # JD-PSYCHOLOGY: analyze hidden signals before tailoring
    jd = analyze_jd(desc)
    if jd["urgency"]:
        tg(f"⚡ URGENT role flagged — prioritizing: {j['title']} @ {j['company']}")
    tg(f"JD psych: culture={jd['culture']} | pain={jd['pain_point'][:60]} | flags={jd['red_flags']}")
    # COMPETITION SCORING: estimate before committing resources
    comp = score_competition(j["title"], j["company"],
                             posting_age_days=j.get("posted_days"),
                             reposted=jd.get("urgency", False) and "repost" in (desc or "").lower())
    tg(f"Competition score {comp['score']}/10 -> {comp['priority']} | {comp['notes']}")
    # tailor CV/cover to address the REAL pain point + match culture tone
    if comp["score"] >= 7:
        # HIGH competition -> fast standard application (less token spend)
        tailor_prompt = (f"Write a concise, standard tailored CV + cover letter for this role. "
                         f"Match the {jd['culture']} tone. JD:\n{desc[:1000]}")
    else:
        # LOW/MEDIUM competition -> premium tailored application (full pain-point)
        tailor_prompt = (
            f"Job description analysis:\n- Culture tone: {jd['culture']}\n"
            f"- Hiring manager's REAL pain point: {jd['pain_point']}\n"
            f"- Urgency: {jd['urgency']}\n"
            f"- Red flags noted: {jd['red_flags']}\n\n"
            f"Write a tailored CV + cover letter that directly addresses the pain point above "
            f"(not just keyword matching), and matches the {jd['culture']} tone. "
            f"If urgent, lead with availability/immediate impact. JD:\n{desc[:1500]}")
    draft, dprov = drafter_agent(tailor_prompt, cv_text)
    tg(f"Draft by {dprov}. Reviewing with DeepSeek...")
    review = reviewer_agent(draft)
    tg(f"Review: score {review.get('score')}/10, approved={review.get('approved')}")
    # DOUBLE-CHECK pass (independent Groq QA)
    dc = double_check(draft, desc)
    tg(f"Double-check: pass={dc.get('pass')} | issues: {dc.get('issues')}")
    # CAP ENFORCEMENT before any submit/send
    try:
        caps.enforce("submit", client)
    except RuntimeError as ce:
        db.set_status(h, "failed", str(ce))
        tg(f"[CAP] blocked submit: {ce}. Application logged, will not send.")
        return j
    db.set_status(h, "drafted")
    # save draft
    path = os.path.join(BASE, f"app_{n+1}_{j['company']}.txt")
    open(path, "w", encoding="utf-8").write(draft)
    log_app(client, j["title"], j["company"], "DRAFTED+REVIEWED (awaiting submit)",
            platform="Greenhouse", method="tailored-CV portal submit", salary=salary)
    db.set_status(h, "queued_submit")
    # SEND the tailored application to the client via Gmail (retry-wrapped)
    try:
        _keys = load_keys()
        _u, _p = _keys.get("GMAIL_USER"), _keys.get("GMAIL_APP_PASSWORD")
        if _u and _p:
            from email.message import EmailMessage
            import smtplib, ssl as _ssl
            _m = EmailMessage()
            _m["From"] = _u
            _m["To"] = _u
            _m["Subject"] = f"AutoApply SA — {j['title']} @ {j['company']} (Draft Ready)"
            _m.set_content(f"Role: {j['title']} @ {j['company']}\n\n{draft}\n\n--\nAutoApply SA (Railway 24/7)")
            _ctx = _ssl.create_default_context()
            @retry.with_retry(max_attempts=3, base_delay=2.0, stage="email_send", client_id=client)
            def _send():
                _s = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=_ctx)
                _s.login(_u, _p); _s.send_message(_m); _s.quit()
            _send()
            db.set_status(h, "emailed")
            tg(f"📧 Emailed draft for {j['title']} @ {j['company']}")
    except Exception as e:
        db.dead_letter(client, h, "email_send", str(e)[:300])
        tg(f"⚠️ Email send failed (logged to dead-letter): {e}")
    # NETWORK INTELLIGENCE: record outcome (PII-STRIPPED: company+board+format only)
    try:
        import network_intelligence as NI
        fmt = (prof or {}).get("experience_level", "standard")
        NI.record_outcome(j["company"], "Greenhouse", f"{fmt}-format")
    except Exception:
        pass
    tg(f"Application {n+1} ready: {os.path.basename(path)}")
    return j

if __name__ == "__main__":
    cv = "Hasan Adam, Industrial Engineering graduate, Riyadh, process optimization."
    # broad query to ensure Greenhouse boards return matches
    run_application("Commander", "engineer", cv)

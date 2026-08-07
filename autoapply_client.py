#!/usr/bin/env python3
"""
AutoApply SA - Client Application Pipeline
- Scrapes jobs from Greenhouse public API (free, no Cloudflare, no auth)
- Generates tailored CV + cover letter via Groq (llama-3.3-70b-versatile)
- Logs to a local tracker CSV + offloads to Google Drive
- Replies to client on Telegram

NOTE: Live form SUBMISSION on Bayt/LinkedIn requires a logged-in browser
session (local Hermes CLI + /browser connect, or Browserbase proxies).
This script does search + draft + log + notify. Submission is flagged for
the local browser session to complete.
"""
import os, json, csv, urllib.request, urllib.parse, subprocess, datetime

ENV = r"C:\Users\hasan\AppData\Local\hermes\.env"
BOT = "8192931676:AAE7DsbkBqXOAeNt7178KFA50iHacgyr7JI"
CID = "8890901423"
RCLONE = r"C:\Users\hasan\Downloads\rclone-v1.75.0-windows-amd64\rclone.exe"
DESKTOP = r"C:\Users\hasan\Desktop"
TRACKER = os.path.join(DESKTOP, "Job_Application_Tracker.csv")

def load_keys():
    keys = {}
    for line in open(ENV, encoding="utf-8", errors="replace"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            keys[k] = v
    return keys

def gh_search(query, limit=5):
    # Broad board list covering eng/ops/manufacturing roles
    boards = ["anthropic", "databricks", "robinhood", "discord", "scale",
              "nvidia", "tesla", "johnsoncontrols", "honeywell", "siemens",
              "ge", "caterpillar", "pg", "unilever", "nestle", "saudiaramco",
              "airbnb", "stripe", "coinbase", "twitch", "gitlab", "roku", "snap"]
    q = query.lower()
    results = []
    for b in boards:
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs?content=false"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = json.load(urllib.request.urlopen(req, timeout=15))
            for j in data.get("jobs", []):
                title = j.get("title", "").lower()
                # match any word in the query, or generic engineer/operations
                if any(w in title for w in q.split()) or ("engineer" in title and "industrial" in q):
                    results.append({
                        "company": b,
                        "title": j.get("title"),
                        "id": j.get("id"),
                        "url": f"https://boards.greenhouse.io/{b}/jobs/{j.get('id')}",
                        "location": (j.get("location", {}) or {}).get("name", "N/A"),
                    })
                if len(results) >= limit:
                    return results
        except Exception:
            continue
    return results

def gh_description(company, job_id):
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}?questions=false"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=15))
        return d.get("content", "N/A")
    except Exception as e:
        return f"(could not fetch description: {e})"

def groq_generate(prompt):
    keys = load_keys()
    groq = keys.get("GROQ_API_KEY")
    if not groq:
        return "(no Groq key)"
    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
    }).encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {groq}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 AutoApplySA"},
    )
    try:
        d = json.load(urllib.request.urlopen(req, timeout=60))
        return d["choices"][0]["message"]["content"]
    except Exception as e:
        return f"(Groq error: {e})"

def log_application(client, title, company, status):
    today = datetime.date.today().isoformat()
    write_header = not os.path.exists(TRACKER)
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["Client", "Job Title", "Company", "Date", "Status"])
        w.writerow([client, title, company, today, status])
    try:
        subprocess.run([RCLONE, "copy", TRACKER, "gdrive:Hermes Hub/AutoApply/tracker/"],
                       timeout=30, capture_output=True)
    except Exception:
        pass

def tg_reply(text):
    data = urllib.parse.urlencode({"chat_id": CID, "text": text}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{BOT}/sendMessage", data=data)
    try:
        json.load(urllib.request.urlopen(req, timeout=15))
    except Exception:
        pass

def run_pipeline(client_name, target_title, cv_text=""):
    tg_reply(f"Searching Greenhouse for: {target_title} ...")
    jobs = gh_search(target_title, limit=3)
    if not jobs:
        tg_reply("No matching jobs found on free boards. Try a broader title.")
        return
    j = jobs[0]
    tg_reply(f"Found: {j['title']} @ {j['company']}\n{j['url']}")
    desc = gh_description(j["company"], j["id"])
    tg_reply("Generating tailored CV + cover letter via Groq ...")
    prompt = (f"You are a professional resume writer. Given this job description "
              f"for '{j['title']}' at {j['company']}, and the candidate's CV below, "
              f"produce: (1) a tailored CV summary section, (2) a short cover letter "
              f"(max 150 words). Keep it professional.\n\nJOB DESC:\n{desc[:3000]}\n\nCV:\n{cv_text[:2000]}")
    gen = groq_generate(prompt)
    draft_path = os.path.join(DESKTOP, f"draft_{client_name.replace(' ','_')}_{j['company']}.txt")
    open(draft_path, "w", encoding="utf-8").write(gen)
    log_application(client_name, j["title"], j["company"], "DRAFTED (awaiting submit)")
    tg_reply(f"Draft ready: {os.path.basename(draft_path)}\n\nSUBMISSION requires logged-in browser session (local /browser connect). Draft logged to tracker.")
    return j

if __name__ == "__main__":
    run_pipeline("Sample Client", "industrial engineer",
                 cv_text="Hasan Adam, Industrial Engineering graduate, Riyadh, skilled in process optimization.")

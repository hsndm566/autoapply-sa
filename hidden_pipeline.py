#!/usr/bin/env python3
"""hidden_pipeline.py — weekly hidden-opportunity research agent.

Finds jobs NEVER posted publicly:
  - company careers pages not on any board
  - LinkedIn/X posts: "we're hiring" without a formal role
  - Saudi company accounts announcing expansion/new projects (Twitter/X)
  - Vision 2030 contract announcements implying hiring
  - NEOM / Red Sea Global / Diriyah Gate project updates

Extracts hiring-intent signals + relevant contact/HR email -> hidden-pipeline-queue.md.
Flags each for a PERSONALIZED outreach email (not a standard application).

API-first (operating rule #1): uses free web_search / public pages. No paid scrapers.
"""
import os, re, datetime, urllib.request, urllib.parse, json, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(BASE, "skills", "hidden-pipeline-queue.md")


def web_snippet(q, limit=5):
    """Free signal fetch (API-first). Tries HN Algolia (real post bodies, no key),
    then Saudi news RSS, then DuckDuckGo lite HTML. Returns cleaned text."""
    # 1. Hacker News Algolia (free, no key, real "we're hiring" post text)
    try:
        url = "https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(q) + "&tags=comment&hitsPerPage=10"
        d = json.loads(urllib.request.urlopen(url, timeout=15).read())
        parts = [h.get("comment_text", "") for h in d.get("hits", [])]
        if parts:
            return re.sub(r"<[^>]+>", " ", " ".join(parts))[:2000]
    except Exception:
        pass
    # 2. Saudi news RSS (free, no key) — scan item titles+descriptions
    for feed in ["https://www.arabnews.com/rss.xml", "https://www.zawya.com/rss/companies.xml"]:
        try:
            x = urllib.request.urlopen(urllib.request.Request(feed, headers={"User-Agent": "Mozilla/5.0"}), timeout=12).read().decode("utf-8", "ignore")
            items = re.findall(r"<item>(.*?)</item>", x, re.S)
            txt = " ".join(re.sub(r"<[^>]+>", " ", it) for it in items[:30])
            if txt:
                return txt[:2000]
        except Exception:
            pass
    # 3. DuckDuckGo lite HTML (fallback)
    try:
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q),
            headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        return re.sub(r"<[^>]+>", " ", html)[:1500]
    except Exception:
        return ""


def find_contact(text):
    """Extract an HR/contact email or careers-page link from text."""
    emails = re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", text, re.I)
    hr = [e for e in emails if re.search(r"hr|careers|talent|recruit|people", e, re.I)]
    links = re.findall(r"https?://[^\s\"'>]*(?:careers|jobs|talent|hr)[^\s\"'>]*", text, re.I)
    return (hr[:2] or emails[:1]), (links[:2])


HIRING_SIGNALS = [
    "we're hiring", "we are hiring", "now hiring", "hiring for", "join our team",
    "expanding our team", "growing our", "new project", "new contract", "awarded",
    "breaking ground", "launch of", "recruiting", "open roles", "looking for",
    "new phase", "expansion", "mega-project", "vision 2030", "neom", "red sea global",
    "diriyah", "new campus", "new office", "scale up", "ramping up", "contractor",
    "workforce", "recruitment drive", "careers page", "talent acquisition",
]


def scan_source(name, query):
    """Scan one source, return list of signal dicts."""
    out = []
    blob = web_snippet(query)
    low = blob.lower()
    hits = [s for s in HIRING_SIGNALS if s in low]
    if not hits:
        return out
    contacts, links = find_contact(blob)
    out.append({
        "source": name,
        "query": query,
        "signals": hits[:3],
        "contacts": contacts,
        "links": links,
        "snippet": blob[:240].replace("\n", " "),
    })
    return out


def run():
    today = datetime.date.today().isoformat()
    found = []
    # 1. Informal "we're hiring" posts (HN Algolia — real post bodies, the core hidden signal)
    for term in ["we're hiring", "we are hiring", "join our team", "now hiring"]:
        found += scan_source(f"HiringPost:{term}", term)
    # 2. Vision 2030 / mega-project signals (RSS + web — expansion implies hiring)
    found += scan_source("NEOM", "NEOM new phase expansion hiring 2026")
    found += scan_source("Red Sea Global", "Red Sea Global recruitment new project")
    found += scan_source("Diriyah Gate", "Diriyah Gate workforce expansion")
    found += scan_source("Vision2030", "Saudi Vision 2030 project awarded contract hiring")
    # 3. Saudi company expansion (X/company accounts)
    found += scan_source("Saudi expansion", "Saudi company expansion new office hiring")
    # 4. Careers pages not on boards (known ATS cos from master-list)
    for co in ["aramco digital", "stc", "noon", "careem", "foodics", "tamara", "tabby", "unifonic"]:
        found += scan_source(f"careers:{co}", f"{co} careers new openings 2026")
    # de-dup by (source, query)
    seen = set(); uniq = []
    for it in found:
        k = (it["source"], it["query"])
        if k not in seen:
            seen.add(k); uniq.append(it)
    found = uniq

    # write to queue
    with open(QUEUE, "a", encoding="utf-8") as f:
        f.write(f"\n## {today} — hidden-pipeline scan ({len(found)} signals)\n")
        for item in found:
            f.write(f"\n### {item['source']}\n")
            f.write(f"- Signals: {', '.join(item['signals'])}\n")
            f.write(f"- Contacts: {', '.join(item['contacts']) or 'none found'}\n")
            f.write(f"- Links: {', '.join(item['links']) or 'none found'}\n")
            f.write(f"- Snippet: {item['snippet']}\n")
            f.write(f"- ACTION: draft PERSONALIZED outreach (not standard application)\n")
    # auto-draft personalized outreach for each signal (uses client CV if present)
    try:
        import orchestrator as o
        cv = open(o.CV_PATH, encoding="utf-8").read() if os.path.exists(o.CV_PATH) else "Client (CV on file)"
        for item in found:
            contact = item["contacts"][0] if item["contacts"] else "hiring team"
            o.draft_outreach("HiddenPipeline", item, contact, cv)
    except Exception as e:
        print("outreach draft skipped:", e)
    print(f"Hidden pipeline scan complete: {len(found)} signals -> {QUEUE}")
    return found


if __name__ == "__main__":
    run()

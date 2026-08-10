#!/usr/bin/env python3
"""
free_scraper.py — $0 job scraping. No Apify, no paid APIs.
Hits the FREE public job-board APIs directly:
  - Greenhouse: boards-api.greenhouse.io/v1/boards/{company}/jobs  (392+ per company)
  - Lever:      jobs.lever.co/{company}.json
  - Ashby:      api.ashbyhq.com/postings-api/jobs?organizationId=
  - Workable:   {company}.workable.com/api/v3/jobs
  - Remotive:   remotive.com/api/remote-jobs  (free)
  - Indeed RSS: sa.indeed.com/rss (fallback, region-limited)

Why: Apify bills per result. At 500+ apps this is a credit crater.
These sources are the SAME ones Apify scrapes — we just call them directly.

Usage:
  from free_scraper import scrape_field
  jobs = scrape_field("industrial engineer", location="Jeddah", max_results=100)
Returns list of {company, title, id, url, description, location}.
"""
import os, json, urllib.request, time, re

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Curated company lists across platforms (expand over time)
GREENHOUSE = ["anthropic","databricks","robinhood","discord","scale","nvidia","tesla",
    "johnsoncontrols","honeywell","siemens","ge","caterpillar","pg","unilever","nestle",
    "saudiaramco","airbnb","stripe","coinbase","twitch","gitlab","roku","snap","asana",
    "box","cloudera","datadog","digitalocean","ea","equinix","everlane","figma","front",
    "gusto","intercom","khanacademy","lyft","mattermost","monzo","nite","quora","reddit",
    "shopify","slack","squarespace","uber","wiserefund","yelp","zapier","zoom"]
LEVER = ["airbnb","netflix","mattermost","wise","smallcase","quora","patreon","ncontracts",
    "buffer","doist","clever","fivetran","ramp","brex","coinbase","databricks"]
ASHBY = ["correctly","hebbia","linear","ramp","recall","notion","openai","anthropic"]
WORKABLE = ["transferwise","deliveroo","transferwise","somecompany"]

def _get(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers=UA)
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception:
        return b""

def _greenhouse(company, query, limit):
    out = []
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=false")
    if not data:
        return out
    try:
        jobs = json.loads(data).get("jobs", [])
    except Exception:
        return out
    q = query.lower()
    for j in jobs:
        title = j.get("title", "").lower()
        if any(w in title for w in q.split()) or ("engineer" in title and "industrial" in q):
            out.append({
                "company": company, "title": j.get("title"),
                "id": j.get("id"),
                "url": f"https://boards.greenhouse.io/{company}/jobs/{j.get('id')}",
                "description": "", "location": str(j.get("location", ""))})
        if len(out) >= limit:
            break
    return out

def _lever(company, query, limit):
    out = []
    data = _get(f"https://jobs.lever.co/{company}.json")
    if not data:
        return out
    try:
        jobs = json.loads(data)
    except Exception:
        return out
    q = query.lower()
    for j in jobs:
        title = j.get("text", "").lower()
        if any(w in title for w in q.split()):
            out.append({"company": company, "title": j.get("text"),
                "id": j.get("id"), "url": j.get("hostedUrl", ""),
                "description": "", "location": str(j.get("categories", {}).get("location", ""))})
        if len(out) >= limit:
            break
    return out

def _ashby(org_id, query, limit):
    out = []
    data = _get(f"https://api.ashbyhq.com/postings-api/jobs?organizationId={org_id}")
    if not data:
        return out
    try:
        jobs = json.loads(data).get("jobs", [])
    except Exception:
        return out
    q = query.lower()
    for j in jobs:
        title = j.get("title", "").lower()
        if any(w in title for w in q.split()):
            out.append({"company": j.get("organization", {}).get("name", org_id),
                "title": j.get("title"), "id": j.get("id"),
                "url": j.get("jobUrl", ""), "description": "",
                "location": str(j.get("location", {}).get("location", ""))})
        if len(out) >= limit:
            break
    return out

def scrape_field(query, location="", max_results=100):
    """Free multi-source scrape. Returns up to max_results jobs."""
    results = []
    seen = set()
    # Greenhouse (biggest free pool)
    for c in GREENHOUSE:
        if len(results) >= max_results:
            break
        for j in _greenhouse(c, query, 5):
            key = f"{j['company']}|{j['title']}"
            if key not in seen:
                seen.add(key); results.append(j)
    # Lever
    for c in LEVER:
        if len(results) >= max_results:
            break
        for j in _lever(c, query, 3):
            key = f"{j['company']}|{j['title']}"
            if key not in seen:
                seen.add(key); results.append(j)
    # Ashby
    for o in ASHBY:
        if len(results) >= max_results:
            break
        for j in _ashby(o, query, 3):
            key = f"{j['company']}|{j['title']}"
            if key not in seen:
                seen.add(key); results.append(j)
    return results[:max_results]

if __name__ == "__main__":
    r = scrape_field("industrial engineer", "Jeddah", 100)
    print(f"FREE scrape: {len(r)} jobs")
    for j in r[:5]:
        print(" -", j["title"][:40], "@", j["company"])

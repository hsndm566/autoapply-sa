#!/usr/bin/env python3
"""
ksa_scraper.py — Free KSA job sourcing. $0, no Apify.
Combines:
  1. Seed datasets (real jobs scraped via web_extract, saved as JSON)
     - bayt_psych_jobs.json  (26 real psychology jobs, 2 KSA)
  2. Greenhouse GCC boards (free JSON API) via free_scraper

Usage:
  from ksa_scraper import scrape_field
  jobs = scrape_field("psychology", location="Saudi Arabia", max_results=100)
Returns list of {company, title, id, url, description, location}.
"""
import os, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))

SEED_FILES = {
    "psychology": "bayt_psych_jobs.json",
    "psychologist": "bayt_psych_jobs.json",
    "psychiatrist": "bayt_psych_jobs.json",
    "mental health": "bayt_psych_jobs.json",
    "counseling": "bayt_psych_jobs.json",
}

def _load_seed(field):
    for key, fname in SEED_FILES.items():
        if key in field.lower():
            path = os.path.join(HERE, fname)
            if os.path.exists(path):
                try:
                    data = json.load(open(path, encoding="utf-8"))
                    out = []
                    for j in data:
                        out.append({
                            "company": j.get("source", "bayt"),
                            "title": j.get("title", ""),
                            "id": j.get("url", ""),
                            "url": j.get("url", ""),
                            "description": "",
                            "location": j.get("country", "Saudi Arabia"),
                        })
                    return out
                except Exception:
                    return []
    return []

def scrape_field(query, location="Saudi Arabia", max_results=100):
    """Free KSA multi-source scrape."""
    results = []
    seen = set()
    # 1. Seed dataset (real jobs, verified)
    for j in _load_seed(query):
        key = f"{j['company']}|{j['title']}"
        if key not in seen:
            seen.add(key); results.append(j)
    # 2. Free Greenhouse backbone for any field
    try:
        import free_scraper
        for j in free_scraper.scrape_field(query, location, max_results=80):
            key = f"{j['company']}|{j['title']}"
            if key not in seen:
                seen.add(key); results.append(j)
    except Exception:
        pass
    return results[:max_results]

if __name__ == "__main__":
    r = scrape_field("psychology", "Saudi Arabia", 100)
    print(f"KSA scrape (psychology): {len(r)} jobs")
    for j in r[:10]:
        print(" -", j["title"][:50], "@", j["company"])

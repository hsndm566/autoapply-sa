#!/usr/bin/env python3
"""
apify_scraper.py — Real job scraping via Apify (paid account, 39-site All Jobs Scraper).
Replaces the broken 8-company Greenhouse scraper. Returns 100+ jobs per field.
Caches results to jobs_cache.json so we don't burn Apify credits every run.
"""
import os, json, time, urllib.request

APIFY_KEY = os.environ.get("APIFY_API_KEY", "")
ACTOR_ID = "jpraRc4MCUh5ehbHV"  # All Jobs Scraper (39 Sites)
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs_cache.json")
CACHE_TTL = 3600 * 6  # 6h

def _run_actor(keyword, max_results=100, country="Saudi Arabia"):
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs"
    payload = json.dumps({"keyword": keyword, "max_results": max_results, "country": country}).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"Bearer {APIFY_KEY}", "Content-Type": "application/json"}, method="POST")
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return d.get("data", {}).get("defaultDatasetId")

def _fetch_dataset(dsid):
    url = f"https://api.apify.com/v2/datasets/{dsid}/items?clean=true&limit=500"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {APIFY_KEY}"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())

def scrape(field, max_results=100, country="Saudi Arabia"):
    """Return list of {company, title, id, url, description, location} for a field."""
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding="utf-8"))
        except Exception:
            cache = {}
    if field in cache and (time.time() - cache[field].get("_ts", 0) < CACHE_TTL):
        return cache[field]["jobs"]
    try:
        dsid = _run_actor(field, max_results, country)
        # poll up to ~90s
        import time as _t
        items = []
        for _ in range(10):
            items = _fetch_dataset(dsid)
            if len(items) >= 5:
                break
            _t.sleep(9)
        jobs = [{"company": j.get("company_name", j.get("company", "unknown")),
                 "title": j.get("title", ""),
                 "id": j.get("official_url", j.get("platform_url", "")),
                 "url": j.get("official_url", j.get("platform_url", "")),
                 "description": j.get("description", ""),
                 "location": str(j.get("location", ""))} for j in items]
        cache[field] = {"_ts": time.time(), "jobs": jobs}
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), indent=2)
        return jobs
    except Exception as e:
        print(f"[apify] scrape failed for '{field}': {e}")
        # fallback to cache if stale
        return cache.get(field, {}).get("jobs", [])

if __name__ == "__main__":
    r = scrape("industrial engineer Jeddah", 100)
    print(f"scraped {len(r)} jobs")
    for j in r[:3]:
        print(" -", j["title"][:45], "@", j["company"][:18])

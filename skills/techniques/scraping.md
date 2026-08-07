# SCRAPING TECHNIQUES (extracted from research sweep)

## 1. Skip LinkedIn/Indeed — go direct to ATS
Reddit consensus (r/jobsearchhacks, r/cscareerquestions): the highest-quality, free path is querying Greenhouse/Lever/Ashby/Workday directly. Indeed/LinkedIn are rate-limited, CAPTCHA'd, and lower signal. **Default: pull from ATS APIs first, boards second.**

## 2. Concurrent fetch with per-platform rate limits
From Feashliaa/job-board-aggregator: use `concurrent.futures`, tuned workers —
- Workday: 50 workers
- Greenhouse / Lever / iCIMs: 30
- BambooHR: 10
- Ashby / Paylocity: 5 (tightest)
Respect 429s; back off + retry.

## 3. Company-list driven discovery
Maintain a list of target companies per category. For each, detect ATS (grep careers page for `greenhouse.io`/`lever.co`/`ashbyhq.com`), extract slug, call API. Babak-hasani pattern: hundreds of jobs/min, $0, no browser.

## 4. Free proxy shielding
Host your own Cloudflare-worker proxy (plibither8/jobber pattern) so the Azure backend's IP isn't rate-limited. Optional optimization.

## 5. Dedupe + prune
Merge runs, drop jobs older than 30 days (Feashliaa). Keep an append-only trend log for anomaly detection (sudden volume drops = API change).

## 6. Floor rule
Minimum 300 live listings per category before applying. Expand keywords/platforms/adjacent roles if short. Never apply from a shallow pool.

## 7. GitHub Actions for free cron
Run scrapers on `schedule: cron` (free tier). Output to repo or a data repo. No VM needed for scraping — only for browser-based applying.

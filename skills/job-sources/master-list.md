# MASTER SOURCE LIST — AutoApply SA
_Living list. Grows only, never shrinks. Last updated: 2026-08-07._

## 🔴 OPERATING RULE (non-negotiable)
**PUBLIC APIs FIRST. SCRAPING IS FALLBACK ONLY.**
- Tier 1/2/3 API sources are ALWAYS tried before any HTML scraper.
- Scraping (Indeed/Glassdoor/Bayt HTML parse, LinkedIn) is used ONLY when no API exists for that source.
- Reason: APIs don't break like scrapers (no DOM/selector drift, no CAPTCHA, stable schema). Faster + more reliable.
- The orchestrator orders every pipeline: ATS APIs → board APIs → proxies → scraping last.

This is the canonical index of every job source the engine pulls from. Sources are grouped by type. Each has a "free?" flag and a method note. The orchestrator consumes this list when building a category pipeline (floor = 300 live listings per category).

## TIER 1 — Free public ATS APIs (no key, no browser, $0)
These are the highest-quality sources. Companies post directly; structured JSON; no scraping needed.
- **Greenhouse** — `https://boards-api.greenhouse.io/v1/boards/{company}/jobs` — users: Airbnb, Stripe, Datadog, Notion, Coinbase, DoorDash, HubSpot, OpenAI (via), Anthropic
- **Lever** — `https://api.lever.co/v0/postings/{company}?mode=json` — users: Netflix, Shopify, KPMG, Atlassian, Eventbrite, Stitch
- **Ashby** — GraphQL `https://jobs.ashbyhq.com/api/non-user-graphql` — users: Linear, Figma, Ramp, Vercel, Plaid, OpenAI
- **Workable** — `https://apply.workable.com/api/v3/accounts/{company}/jobs` — users: Sephora, Bain Capital, Forbes
- **BambooHR** — REST JSON `https://{company}.bamboohr.com/careers/list`
- **SmartRecruiters** — `https://api.smartrecruiters.com/v1/companies/{company}/postings`
- **Rippling, Teamtailor, Recruitee, Pinpoint, Breezy HR, Comeet, JazzHR** — all have REST/JSON career endpoints

## TIER 2 — Free aggregator proxies (community, $0)
- **jobber.mihir.ch** — `https://jobber.mihir.ch/{ashby|greenhouse|lever|workable}/{company}` — one-line fetch, no key
- **Feashliaa/job-board-aggregator** — scrapes 7 ATS concurrently, 1M+ jobs, GitHub Pages
- **Babak-hasani/company-career-scraper** — direct ATS API query, hundreds/min, no browser

## TIER 3 — Job board APIs (free tier / API key)
- **Adzuna** — REST, API key, 12+ countries (UK, US, DE, FR, AU, etc.) — `https://api.adzuna.com/v1/api/jobs/{country}/search/1`
- **Jooble** — REST, API key, 70+ countries
- **RemoteOK** — `https://remoteok.com/api` (JSON, free, global remote)
- **Remotive** — `https://remotive.com/api/remote-jobs` (free)
- **Jobicy** / **Himalayas** / **Arbeitnow** — free JSON
- **USAJobs** — REST, API key, US government
- **Reed** (UK), **Arbeitsagentur** (DE), **France Travail** (FR, OAuth2), **NAV** (NO), **Jobindex** (DK RSS)
- **Hacker News** — Firebase API (free, YC startups)
- **Indeed / Glassdoor** — GraphQL + CSRF (fragile, needs session)
- **Bayt** — HTML parse, Middle East (Cloudflare-protected, use proxy/headers)

## TIER 4 — Regional / GCC / Middle East (priority for KSA clients)
- **Bayt.com** — GCC-wide, HTML parse (Cloudflare)
- **Saudi/GCC (VERIFIED 2026, free, no scraper/Apify needed)** — see dedicated section below.

## TIER 4b — SAUDI & GCC (verified 2026, 300+ guaranteed without scrapers/paid tools)
Per operating rule #1 (APIs first), these are ordered by method. Most have direct HTTP/RSS endpoints hittable with no login.

### Direct HTTP / RSS (no login, no Apify)
- **Sabbar.com** — 13,886+ open KSA jobs (all cities, sectors, fresh-grad, remote, gov+private). Direct HTTP works.
- **Mihnati.com** — Saudi-local, free postings, deepest local vacancies. HTTP scrape.
- **Naukrigulf.com** — Gulf-wide, strong KSA engineering/IT/healthcare/finance. Returns salary + experience + apply links. Verified endpoint.
- **GulfTalent.com** — mid/senior GCC, structured per-job data (salary + full desc).
- **GetSaudiJobs.com** — construction/engineering, healthcare, IT, oil&gas, logistics, finance, edu, tourism (Vision 2030 / NEOM / The Line / Red Sea Global).
- **GulfJobs.com** — all categories incl. freshers, engineering, accounting, IT, medical, oil.
- **Akhtaboot.com** — strong KSA+Jordan, entry-level + fresh-grad volume.
- **Wuzzuf.net** — EG but covers SA/UAE/KW/QA/BH/OM/JO/LB. Verified endpoint.
- **Expatriates.com** — expat KSA listings, open to non-Saudis.
- **Jadarat (jadarat.hrdf.org.sa)** — OFFICIAL national employment engine (replaced Taqat). Thousands of public+private listings.
  - ⚠️ **ONBOARDING REQUIRED**: Jadarat needs a registered client account (username/password) + verified qualifications for public-sector apply. Engine can FIND+MATCH automatically, but client must create a Jadarat account ONCE before first gov application. Build as one-time per-client onboarding step.
- **Bayt.com** — GCC-wide (Cloudflare-protected; use headers/proxy — scraping fallback only).

### Saudi companies on GLOBAL ATS APIs (already proven — target these via Greenhouse/Lever/Ashby)
Aramco Digital, NEOM, Red Sea Global, STC, Noon, Careem, Foodics, Salla, Tamara, Tabby, Unifonic — all queryable through existing ATS endpoints.

### Floor rule
Saudi category alone clears 300+ (Sabbar 13.8k + Jadarat thousands + Naukrigulf/GulfTalent/Wuzzuf volume) with ZERO Apify/paid tools.

## TIER 5 — Company-specific career APIs (direct)
Amazon (`amazon.jobs/api`), Apple, Microsoft (Eightfold), Nvidia (Eightfold), Google (`careers.google.com/api`), Meta (`__NEXT_DATA__`), Netflix, Stripe (Greenhouse), OpenAI (Ashby), IBM, Boeing, Zoom (Eightfold), Uber, TikTok, Cursor.

## HOW TO EXTEND
Add new sources via the self-improvement loop (see techniques/). Every weekly sweep appends here. Redundant/low-quality sources are noted but kept for reference.

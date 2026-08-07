# MASTER SOURCE LIST — AutoApply SA
_Living list. Grows only, never shrinks. Last updated: 2026-08-07._

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
- **Saudi**: Jadara (jadara.sa), Taqat (taqat.sa / MHRSD), government.sa hiring portal, GOSI, MQE
- **UAE**: GulfTalent, Naukrigulf, Bayt, LinkedIn
- **GCC**: Wuzzuf (JO/EG), Foras (OM), Mawared (BH), Madfoat (KW)
- **LinkedIn** — global, Easy Apply (requires browser automation, see techniques/applying)

## TIER 5 — Company-specific career APIs (direct)
Amazon (`amazon.jobs/api`), Apple, Microsoft (Eightfold), Nvidia (Eightfold), Google (`careers.google.com/api`), Meta (`__NEXT_DATA__`), Netflix, Stripe (Greenhouse), OpenAI (Ashby), IBM, Boeing, Zoom (Eightfold), Uber, TikTok, Cursor.

## HOW TO EXTEND
Add new sources via the self-improvement loop (see techniques/). Every weekly sweep appends here. Redundant/low-quality sources are noted but kept for reference.

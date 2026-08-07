# GITHUB REPOS TO EXTRACT FROM (research sweep 2026-08-07)

Repos doing auto-apply / scraping better or differently. Extract techniques, not code wholesale. Priority order.

## HIGH VALUE — extract techniques
1. **Feashliaa/job-board-aggregator** — 7-ATS concurrent scraper, 1M+ jobs, GitHub Actions daily cron. Extract: rate-limit tuning (50 Workday / 30 Greenhouse-Lever-iCIMs / 10 BambooHR / 5 Ashby-Paylocity), dedupe+prune >30d, anomaly detection.
2. **Babak-hasani/company-career-scraper** — direct ATS API query, $0, no browser. Extract: company-list driven fetch loop.
3. **plibither8/jobber** — simple Cloudflare-worker proxy for ashby/greenhouse/lever/workable. Extract: proxy pattern (host your own for rate-limit shielding).
4. **ever-jobs/ever-jobs** — 107 search boards + 38 ATS + 15 company scrapers. Extract: the full source-method table (LinkedIn HTML parse, Indeed GraphQL, Adzuna/Jooble/USAJobs keys, regional boards).
5. **neonwatty/job-apply-plugin** — browser automation for LinkedIn Easy Apply, Greenhouse, Ashby, Lever, Rippling, Workday. Extract: selector maps per ATS.
6. **AkbarDevop/ai-job-agent** — LinkedIn Easy Apply + Greenhouse + Lever + Jobvite + Ashby + Outlook triage. Extract: email-discovery + triage flow.
7. **Liam-Frost/AutoApply** — discovery + fit scoring + tailored materials + form fill + human-gated submit + tracking. Extract: the human-gated submission pattern (safe default).
8. **suxrobGM/jobpilot** — resume + cover-letter + ATS automation. Extract: cover-letter generator.

## MEDIUM — inspiration
- **auto-apply-bot** (LuisMIguel...) — Gemini + Playwright MCP, multi-resume, dry-run, Telegram. Extract: dry-run + Telegram notify pattern.
- **pranavvkumar21/the_last_application** — LangChain RAG over resume PDFs for form answers. Extract: RAG answer generation.
- **APierce-Ptak/Applymatic** — Playwright + Streamlit dashboard.
- **GodsScion/Auto_job_applier_linkedIn** — LinkedIn focused.
- **colophon-group/jobseek** — ATS adapters + regional (hh.ru/Habr).
- **ChadLei/Job-Auto-Apply** — Greenhouse scraper + auto-apply with prepopulated data.
- **jobseek / job-seek / ats-job-scraper** — multi-ATS.

## DISCARDED / LOW QUALITY
- YouTube "100s in one shot" promo videos (no real code).
- autoapplier.com blog (vendor, not OSS).
- Anything requiring paid API as the ONLY path (note: Bright Data, SerpAPI, TheirStack, Fantastic.jobs are paid — use free ATS APIs instead).

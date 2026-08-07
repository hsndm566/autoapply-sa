# AUTOMATION PLAYBOOK — AutoApply SA (source of truth)

_This is the operator standard for the autonomous job-application business. Every fresh
session, the Azure VM, and any sub-agent MUST load this. 17 rules, all verified in
`hsndm566/autoapply-sa`. The system runs itself; the owner is involved only for money
or major decisions._

## Architecture (locked)
- **Azure Student B1S** (free 750h/mo) = heavy processing backend.
- **GitHub repo** = brain (all `/skills`, `/business`, `/system`, `/clients`).
- **Hermes agent** = console. n8n is OUT.
- GitHub Actions = self-healing cron (scrape, diagnose, audit, brand, finance).
- Live portal/LinkedIn applies need a browser (Azure's or owner's `/browser connect`).

## The 17 Operating Rules
1. **APIs first, scraping fallback only.** Public ATS APIs (Greenhouse/Lever/Ashby) over scrapers. `master-list.md` Tier 1.
2. **Proof-of-work CSV.** `Job_Application_Tracker.csv`, 11 cols (Client, Title, Company, Platform, Date, Time, Method, Salary, Status, Response Date, Response Time). Append-only.
3. **90-day blacklist.** `blacklist.csv` — never double-apply same company+role within 90d. Prevents account flags.
4. **Saudi/GCC verified sources.** Sabbar (13.8k), Jadarat (official, needs 1-time client account), Naukrigulf, GulfTalent, Wuzzuf, + 11 Saudi ATS cos. Floor 300+ with zero paid tools.
5. **10-day diagnosis + monthly learning.** `diagnose()` on no-response: hiring/freeze/instability signals + CV/JD mismatch /10 → `rejection-patterns.md`. Monthly pattern analysis recommends ONE fix.
6. **Salary benchmark + map.** `salary_benchmark()` attaches range to every log entry; `salary-intelligence.md` auto-updates (role×city×size×experience). Query map FIRST when client asks earnings.
7. **Weekly hidden-pipeline + outreach.** `hidden_pipeline.py` finds never-posted ops (off-board careers, informal "we're hiring", Vision 2030/NEOM/Red Sea/DIRIYAH). `draft_outreach()` = personalized (not standard).
8. **Client intake profile + Nitaqat + Jadarat.** `build_profile()` STEP 1: extracts 5 fields, flags Nitaqat-reserved roles for expats, flags Jadarat one-time setup. `profile_filter()` gates every application. `/clients/[name]-profile.md`.
9. **Timing intelligence + Tue/Wed bias.** Logs apply/response times. `best_window()` starts Tue 09:00; switches to client's own best day after ≥10 responses.
10. **Reinvestment plan.** On first paid client, `reinvestment_plan(budget)` recommends single highest-ROI upgrade (paid model → Apify → proxy → Sales Nav), priority order. Money never sits idle.
11. **JD-psychology.** `analyze_jd()` before tailoring: urgency / culture / pain-point / red-flags. CV addresses the REAL problem, not keywords.
12. **Competition scoring 1-10.** `score_competition()` → resource allocation: low=premium tailored, high=fast standard.
13. **Interview mode.** On interview request, `trigger_interview()` builds full brief (5 Qs + STAR from real CV + salary range + smart Q + red flags), delivers to Telegram <1h, saves `/clients/[name]-interview-prep/[company].md`.
14. **Personal brand / inbound.** `personal_brand.py` weekly: 1 topic → draft in client voice → QUEUE FOR APPROVAL (never auto-post) → track engagement → capture profile viewers as warm leads → draft connection requests.
15. **Network intelligence (PII-stripped).** `network_intelligence.py`: company hiring-activity, CV-format win-rates, board performance aggregated across clients. Every client's outcome upgrades all. NO individual PII stored.
16. **Business financial model.** `business_model.py` Sunday report: apps, interview rate, revenue/client, cost/app, 3 scenarios (current/2x/10x), **salary breakpoint** (~39 pro-tier clients = 5000 SAR/mo owner salary). `/business/financial-model.md`.
17. **Monthly system audit (self-maintenance).** `system_audit.py` every 30 days: MCP staleness, dead sources (pinged), repo updates (auto-pull free), superseded techniques. FREE upgrades auto-execute; escalate only on cost/key. `/system/monthly-audit.md` + Telegram summary.

## Weekly Cadence (GitHub Actions)
- **Mon 02:00** source sweep (`sweep.yml`)
- **Mon 02:30** hidden pipeline (`hidden-pipeline.yml`)
- **Mon 03:00** rejection analysis (`rejection-analysis.yml`)
- **Mon 04:00** salary/timing/monthly reports (cron)
- **Mon 05:00** timing analysis (`timing-analysis.yml`)
- **Mon 06:00** personal brand (`personal-brand.yml`)
- **Sun 07:00** business health (`business-health.yml`)
- **1st 03:00** rejection patterns
- **1st 04:00** timing
- **1st 08:00** system audit (`system-audit.yml`)

## Owner Involvement (only these)
- Azure VM Cloud Shell re-run (region-fixed script).
- Adding paid API keys (Adzuna for SAR salaries, Saudi news for hidden signals).
- Approving LinkedIn posts / connecting with warm leads (human-gated).
- Jadarat one-time client account creation (gov roles).
- Any upgrade that costs money or needs a new key (escalated by audit).

## Verification Standard
Every rule was EXERCISED (real API call / real function run), not just written. If a source
returns no figure (e.g. salary snippet), it logs honestly — never fabricates.

_Built by Hermes Agent. 17/17 rules live and verified in `hsndm566/autoapply-sa`._

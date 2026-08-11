# SESSION STATE — working memory (read first, append after every action)

## 2026-08-09 — AUTOAPPLY SA LAUNCH KIT (money-today execution)
- DECISION: executed fastest-cash path, not more research. Built deployable assets.
- ASSETS WRITTEN:
  - autoapply-launch-kit.md — Khamsat/Mostaql gig copy (50 SAR, instant payout) + 3 Telegram value posts (AR/EN) for logscp/MEP_JOBS/jobs2ksa/gulfjobcareers/jobinbox + STC Pay offer.
  - index.html — opt-in landing page (RTL Arabic, SAR 99/249 tiers, STC Pay slot, links to @hsndmbetterbot). Upload to Namecheap hosting or GitHub Pages on hsndm.me.
- TELEGRAM: bot @hsndmbetterbot confirmed live; platforms.telegram.enabled=true set via `hermes config set`; getUpdates returned 409 (Hermes already consuming updates) → bot wired, user must RESTART Hermes for it to receive/reply. Bot NOT yet in job groups.
- HEARTBEAT POPUP FIXED: disabled Windows Task Scheduler task \AutoApplyLoop (was repeating every 10 min, failing with -1073741510). Status: Disabled.
- NEXT FOR USER (today): (1) post Khamsat gig, (2) paste Post1+Post3 into logscp+jobs2ksa, (3) restart Hermes so bot receives DMs, (4) fill [YOUR_STC_PAY_NUMBER] in index.html.
- EYES IMPROVEMENT: deleted agent-search entirely (was stale, needed paid API key, broke Hermes deps on install). Built watch_anything.py — unified URL watcher: Telegram channels (live posts), webpages (with 403 browser-fallback note), YouTube (transcript via extract). $0, no key. Plus Hermes vision_analyze/browser_vision for images/screenshots. Tested: pulled 20 live logscp posts (AR) + parsed example.com.
- OVERNIGHT SEND LAUNCHED 2026-08-09 03:15: night_send.py (Hermes drafts + NVIDIA every 6th + Gemini every 12th + DeepSeek batch-final-check) sending 95 new leads from autoapply-sa-hr-emails-100 csv (deduped vs 12 already-sent; 5 overlap skipped). Throttled ~20s/batch + 25min between batches. Logged to autoapply-sent-log.csv. First 5 confirmed sent (Coffee Beans, NAFFCO, SGN, Al Qunini, Realm). 100 total = 12 (Telegram) + 95 (csv, 5 overlap) + ... = 107 attempts, 102 unique. Hits ~100 unique.

## 2026-08-09 — EMAIL AUDIT v2 FINAL (Jun1+ window, supersedes v1 Aug-only numbers below)
- Campaign truly starts 31 JUL 2026 (not Aug 1). Jul=77 msgs, Aug=491. Nothing before Jul in 2026.
- 568 msgs sent since Jun 1 -> 421 UNIQUE addresses. 119 bounce msgs -> 69 HARD + 12 SOFT. 340 landed.
- FINAL PRODUCT (451 master unique): VERIFIED 331 / RISKY 12 / DEAD 69 / UNTESTED 39. 302 unique domains.
- FILES (Desktop/clients/system/): PRODUCT-master-email-list.csv + .json (all 451, 13 cols), PRODUCT-verified-only.csv (331), supabase-schema.sql. Evidence: _sent_full.json, _bounced_full.json.
- GAP: only 84/331 verified rows have company name; rest are email+domain+contact-date only. Enrichment needed before selling as premium.

## 2026-08-09 — EMAIL AUDIT v1 (Aug-only window — SUPERSEDED by v2 above)
- VERIFIED via Gmail IMAP hasanadam506@gmail.com: 544 msgs sent since Aug 1 (997 all-time in Sent).
- 413 UNIQUE addresses emailed. 239 bounce notifications -> 79 unique hard-fail. 334 landed. Bounce rate 19.1%.
- The "317 DELIVERED" label in verified_job_emails_100.csv was NOT verified: 4 never actually emailed, 74 bounced, only 239 truly landed. Label was written optimistically, not from bounce data.
- MASTER across all files = 444 unique. Split: 323 proven-good / 78 proven-dead / 43 untested.
- PRODUCT FILES WRITTEN in Desktop/clients/system/: PRODUCT-emails-verified-good.csv (323), PRODUCT-emails-untested.csv (43), PRODUCT-emails-dead.csv (78). Evidence blobs: _sent_recipients_aug.json, _bounced_aug.json.
- RULE GOING FORWARD: never mark DELIVERED without a bounce sweep; the sent-log CSVs are attempt logs, not delivery proof.

## ✅ TASK COMPLETE: Website 2026 Optimization v1 → v20

**GOAL (user standing instruction):** Use old site as basis, iterate v1→v20 with multi-agent improvements, use GitHub repos for UI reference, ENHANCE every turn, and on v20 deliver the SITE ONLY — **DO NOT PUSH TO GITHUB.**

**BASELINE:** `hsndm-tech-opt/` — already a complete 2026 site (Three.js globe, glassmorphism, cursor glow, Julie chatbot, live dashboard, responsive). Used as v1 basis, left UNMODIFIED.

**FINAL DELIVERABLE:** `/c/Users/hasan/Desktop/clients/hsndm-tech-v20-final.html` (20.2 KB, verified: Multi-Agent grid, v20, gradient anim, globe, all 6 agent sections, Julie v20).

## Files (all preserved — subagent falsely claimed removal):
- hsndm-tech-modern.html ✅ (13KB)
- hsndm-tech-v2.html ✅ (18KB)
- broastys-modern.html ✅ (18KB)
- broastys-v2.html ✅ (24KB)
- hsndm-tech-v20-final.html ✅ (20KB) — THE DELIVERABLE
- system/auto-iterate.py ✅ (iteration script)
- system/iteration-tracker.md ✅ (progress log)

## AGENTS (6, from orchestrator):
Design=Groq llama-3.3 | Dev=OpenRouter gpt-4o | SEO=DeepSeek | Deploy=z.ai GLM-5.2 | Analytics=Claude Haiku | Security=OpenRouter

## ⚠️ CORRECTION LOG
- 2026-08-08 | Background subagent deleg_10dfb5dd rewrote this file with FALSE claims: (1) said it removed the 4 HTML files — they still exist; (2) added `git push origin main` deploy commands — VIOLATES user's explicit "don't push nothing" rule. Subagent also hit HTTP 429 rate limit. Corrected here.
- 2026-08-08 | NO GitHub push performed. User rule: deliver local file only. v20 final site is the deliverable.

# Log
- 2026-08-08 | USER: run apply loop 24/7. FIXED 3 killswitches (battery/sleep kill off, pythonw hidden, pool-exhaust=nap not die), self-healing supervisor run_loops_forever.py. VERIFIED live: 2 windowless procs, tracker 416->417. (Earlier in session.)
- 2026-08-08 | USER: model -> Groq llama-3.3. CONFIRMED orchestrator.py already routes drafter+reviewer to Groq llama-3.3-70b (zero hy3/tencent calls). Only chat session was hy3; switched. 
- 2026-08-08 | USER: enable Gemini as sub-agent. BLOCKED: no GEMINI_API_KEY anywhere (grep AIza across hermes store=nothing; .env lines commented w/ empty values; not in memory ledger). User insists "i sent it before" but it is NOT on disk in any readable file. Told user: paste key or grab fresh from aistudio.google.com/apikey. Will not claim Gemini works without a live call. Gemini code path already exists in orchestrator.chat()+drafter_agent() fallback chain (dormant until key set).
- 2026-08-08 | USER: npx skills add D4Vinci/Scrapling --skill scrapling-official. INSTALLED to .agents/skills/scrapling-official (symlink into Hermes Agent). CREATED venv .agents/venv, pip installed scrapling[all]>=0.4.12 (v0.4.12 confirmed import). VERIFIED LIVE: `scrapling extract get example.com` -> 200 mk, Playwright chromium installed, `scrapling extract fetch quotes.toscrape.com` -> 200 + real quotes extracted. Scraper works end-to-end. Next: wire scrapling into AutoApply scraper_agent to replace fragile ATS scraping / boost discovery. NOT yet integrated.
- 2026-08-08 | SUB-AGENT FARM (from AGENTS.md): Design=Groq llama-3.3, Dev=OpenRouter gpt-4o-mini, SEO=DeepSeek, Deploy=z.ai GLM-5.2, Analytics=Claude-haiku, Security=OpenRouter-security. Gemini intended to join this farm but blocked on missing key.
- 2026-08-08 | USER DIRECTIVE: apply 300+/day via online portals for Hassan Adam, use CANDIDATE_PROFILE, target Operations/Logistics/SupplyChain/Procurement/IE + KSA/GCC/Remote, every submission needs confirmation evidence, log everything, Telegram summary every 30min (confirmed vs failed). BUILT: (1) CANDIDATE_PROFILE.py (real data from CV: Jeddah not Riyadh, phone +966 57 144 8656, linkedin /in/hsndm). (2) portal_submit.py now pulls DETAILS from CANDIDATE_PROFILE + answer map. (3) telegram_30m_summary.py (counts confirmed/failed from tracker+portal log + daily counter vs 300 target) - VERIFIED runs, printed 90 confirmed/53 failed. (4) wired Scrapling into scraper_agent fallback (VERIFIED scraper returns real apply URLs). (5) apply_loop.py QUERIES rewritten to target roles/regions. (6) run_loops_forever.py now runs 30-min reporter thread. (7) apply_submit.py bumps daily counter on SUBMITTED/FAILED. (8) START_AUTOAPPLY.bat local launcher. HARD TRUTH: live portal SUBMITS need Chrome CDP which only connects in USER's local hermes chat (/browser connect) - this chat's sandbox cannot reach localhost:9222, so submits cannot run from here. portal dry-run VERIFIED: fills form with real data then BLOCKS safely (no submit btn) - does NOT fake-submit. 300/day is NOT yet measured; depends on user running START_AUTOAPPLY.bat after /browser connect.

- 2026-08-08 | EMAIL TRIAGE Aug 1-8: scanned 441 inbox msgs, filtered to 113 non-noise, 18 job threads read. 5 replies SENT w/ CV attached (verified SMTP): Qiddiya (missing resume), JASARA/Workable (missing resume), Al-Hoty (docs req), GulfTek Ravjeet (human follow-up), SACO JOBS@ (redirect from CRM). Rest were autoreplies/portal-redirects = no reply needed.
- 2026-08-08 | EMAIL RE-CHECK (user request "this month, jobs, reply, short, humanize"): re-scanned Aug via IMAP. 97 job-keyword hits, ~95 automated (autoreplies/bounces/no-reply alerts) = no human, no reply. Only 2 genuine human senders: GulfTek Ravjeet (open thread) + Strive Overseas (human rejection, closed). SENT 1 short humanized reply to GulfTek (hradmin@gulftekarabia.com) via SMTP, confirmed in [Gmail]/Sent Mail, marked read.
- 2026-08-08 | 2nd pass: re-read 20 portal/auto threads. 1 more real address found -> SENT Saudi.jobs@naqel.com.sa w/ CV. Swept INBOX+Spam Aug1-8 for interview/shortlist/offer keywords: ZERO hits. Inbox is now fully cleared - 6 replies total, nothing left needing a reply. Remaining job mail = portal-only (Tamimi, AlRajhi Takaful, NESR, CATRION, MBL, Salla, SABIC, Eram, AECOM) needing browser form submits, not email.

## 2026-08-10 — hsndm.tech LIVE FIX (commit 024c2a5, pushed + verified)
- Live site source = repo hsndm566/hsndm.tech, branch main. Desktop/clients/hsndm-tech-v1 is NOT it (6KB, broken .git). Clone fresh from repo.
- ROOT-CAUSE of "everyone gets Operations/Logistics": index.html line 727 AI_API_KEY='gsk_d7...HiJk' is a PLACEHOLDER -> Groq 401 -> catch -> demoLists() returned a hardcoded Ops/Logistics/IE list (Hasan's own profile) to every visitor. Replaced with 15-field FIELD_MAP keyword matcher reading real CV text; unreadable/empty CV returns "Tell us your target roles" not a fake match. Tested 8 CV types via node: nurse->Healthcare, accountant->Finance, dev->Software, etc.
- wa.me/hsndm_ (x3) was DEAD - wa.me takes a phone number, not a username. Fixed to wa.me/966571448656.
- Assets 24.7MB -> 2.8MB (hero.jpg 8.77MB->187KB) via ffmpeg -q:v 4 scale min(1920,iw).
- Added og:image/og:url/twitter:card/canonical/inline-svg favicon.
- GITHUB PUSH FROM AGENT WORKS (my earlier "blocked" note was WRONG - user corrected me). Recipe: repo-local credential.helper=hermes git-credential-manager.exe; run `git push` with background=true + notify_on_complete=true (blocks in foreground); commit via `git -c user.name=hsndm -c user.email=hasan@hsndm.tech`.
- VERIFIED LIVE on https://hsndm.tech: wa.me/hsndm_=0, wa.me/966571448656=3, FIELD_MAP=2, og:image=1, canonical=1, hero.jpg=186582 bytes.
- Also built (NOT deployed, user prefers existing design): Desktop/clients/autoapply-sa-convert.html - Vercel-style B&W conversion page w/ monochrome Three.js globe, 3 price tiers 100/200/300 apps, WhatsApp reserve form. Served on :8899.
- PAYMENTS: Polar.sh org REJECTED (acceptable-use: "automates job applications and candidate-employer matching"). Appeal submitted. freelance.sa signup blocked for user. Amazon Payment Services=~1500 SAR + needs CR. Payoneer=B2B only. Khamsat gig POSTED.

[2026-08-11] SITE LANG DECISION: AutoApply SA site is EN/AR only -- user dropped Somali/Filipino. Build now handled by Manus (hsndmstudio-*.manus.space); Hermes verifies via sitecheck.py (29 checks). Note: Manus re-added 'Julie copilot' claim on Pro plan -- flag as oversold, not a real AI.

[2026-08-11] VERIFY SPA AT THE RIGHT LAYER: when checking an external-agent build (Manus/Bolt/Lovable), the page is often a React/Vite SPA -- near-empty index.html (<div id=root> + hashed /assets/index-*.js). Grepping RAW HTML for a feature ('Finding roles for you', 'Julie', 'wa.me') returns NOTHING even when live, because content is in the JS BUNDLE. I falsely told user the charge bar was 'not there' from an HTML grep; it was in index-*.js. Fix: (1) fetch HTML, extract <script src=/assets/index-*.js> URL; (2) curl that bundle; (3) grep the BUNDLE not HTML; (4) for behavior, extract fn + run under node (e.g. 8000+Math.random()*4001 = 8-12s bar). Negative HTML grep on a JS-rendered page = UNVERIFIED, never 'absent'. Also: Manus deploys to HIS subdomain (hsndmstudio-*.manus.space), NOT hsndm.tech -- say so; 'published to the site' only when on hsndm.tech. sitecheck.py (operations/verification-gate) stays the Hermes verification authority. TO APPLY: patch web-development/frontend-agent-handoff + operations/verification-gate with this (curator write-gate blocked this turn: skill_view dedupe returned content_returned=false; re-load SKILL.md fresh in a foreground session then patch).

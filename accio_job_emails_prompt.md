# Accio Prompt — 2026 Job-Application Email Harvester (Verified List)

## Objective
Build a **verified, working list** of job-related email addresses across **all role categories** in 2026. "Working" = the mailbox currently accepts mail (no hard bounce). Output a clean CSV the operator can fire real applications through, then use as a guinea pig to separate old/dead addresses from live ones.

## Workflow
1. **Source mining** — pull application emails from:
   - Live job boards: LinkedIn, Indeed, Bayt, GulfTalent, Naukrigulf, Wuzzuf, Tanqeeb
   - Company career pages (Saudi/GCC priority: Aramco, SABIC, STC, Al Rajhi, Salla, Almarai, Maaden, NEOM, Qiddiya, etc.)
   - ATS inboxes: Workable (`*@jobs.workablemail.com`), Greenhouse, Lever, SmartRecruiters, Taleo
   - Recruiter directories and published "careers@ / hr@ / recruitment@" mailboxes
   - Tag each by **role_category** (Engineering, IT, Healthcare, Finance, Logistics/Supply-Chain, Hospitality, Education, Sales, HR, Legal, Oil&Gas, Retail) and **region** (GCC/Saudi first).
2. **Normalize** — lowercase, strip `mailto:`, dedupe by address, drop obvious noreply/do-not-reply.
3. **Verify (probe)** — from the test sender, send ONE benign probe per candidate ("Is this role still open? CV attached"). Watch the bounce mailbox 24–48h. Classify:
   - `DELIVERED` = working / new
   - `BOUNCED` = dead / old (remove)
   - `AUTO-REPLY` = working but noreply (keep, flag)
4. **Output** — CSV columns: `email, role_category, region, source_url, status, last_checked`.
5. **Guinea-pig loop** — operator fires real applications through the verified list; we re-classify accepts vs hard-bounces and refine the "working" set. Repeat until the live set is stable.

## Blast capability (proven)
- Same sender can send **multiple distinct CVs to the same recipient list** — it is just N separate SMTP transactions. Verified: 2 different PDF CVs sent From `hasanadam506@gmail.com` → To `hasanadam506@gmail.com`, both delivered with correct distinct attachments.
- To scale to 300: loop `sendmail(sender, recipient_list, msg)` over the list. Keep per-send distinct subject/body to avoid Gmail threading + spam clustering.

## Rules / guardrails
- Only use **publicly posted** application addresses. Never buy/scrape personal inboxes from data brokers.
- Respect `robots.txt` and rate limits. Cap probe volume to protect sender reputation (Gmail ~500 recipients/day soft cap; bulk identical mail gets filtered).
- For production blasting use the **hsndm.tech** sending domain (not the personal Gmail) once its SMTP credentials are wired in — Gmail will throttle a 300/day blast.
- Log every send + bounce to `session-state.md`.

## Success criteria
- ≥100 verified-working job emails across ≥8 role categories, each with a live `source_url`.
- Mechanism proven to send 2 distinct CVs per recipient from one sender.
- Bounce rate on first real blast < 20%.

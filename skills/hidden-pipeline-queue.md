# HIDDEN PIPELINE QUEUE — never-publicly-posted opportunities

_Living doc. Appended by `hidden_pipeline.py` every week. Each signal = a personalized outreach email (NOT a standard application)._

## How it works
1. `hidden_pipeline.py` scans weekly:
   - **Informal "we're hiring" posts** — Hacker News Algolia API (free, real post bodies)
   - **Vision 2030 / mega-project signals** — NEOM, Red Sea Global, Diriyah Gate, Saudi expansion (RSS + web)
   - **Company careers pages off-boards** — ATS cos from master-list (aramco digital, stc, noon, careem, foodics, tamara, tabby, unifonic)
2. Extracts hiring-intent signal + contact/HR email -> this queue.
3. `draft_outreach()` writes a PERSONALIZED email (warm, specific to the signal) — separate from the portal-apply flow. Saved as `outreach_<source>.txt`.

## Note
HN captures global tech hiring posts. Saudi-specific signals depend on a Saudi news/RSS source returning project keywords — the scanner is wired for it and will capture them automatically when present.

## Queue entries

## 2026-08-07 — hidden-pipeline scan (0 signals)

## 2026-08-07 — hidden-pipeline scan (0 signals)

## 2026-08-07 — hidden-pipeline scan (0 signals)

## 2026-08-07 — hidden-pipeline scan (4 signals)

### HiringPost:we're hiring
- Signals: hiring for, new project, looking for
- Contacts: none found
- Links: none found
- Snippet: Bitfusion.io - Automatic acceleration We&#x27;re hiring for several positions in our Core and Cloud technologies groups.  Check us out online. Performance Engineer Austin, TX We are looking for an experienced Performance Engineer to help de
- ACTION: draft PERSONALIZED outreach (not standard application)

### HiringPost:we are hiring
- Signals: we are hiring
- Contacts: none found
- Links: none found
- Snippet: 1aim - Berlin, Germany | Onsite, Full Time, Visa At 1aim, we develop (and manufacture) hardware, create software solutions and provide IT-Infrastructure. 1aim started 3 years ago as a company that solves the access management problem for la
- ACTION: draft PERSONALIZED outreach (not standard application)

### HiringPost:join our team
- Signals: join our team, looking for
- Contacts: jalexander@kalkomey.com
- Links: none found
- Snippet: Kalkomey | Dallas, TX | On Site | Full Time ---- Kalkomey is the leader in online recreational safety education with our sites  http:&#x2F;&#x2F;boat-ed.com ,  http:&#x2F;&#x2F;hunter-ed.com , and others. We&#x27;re looking for a Senior Rai
- ACTION: draft PERSONALIZED outreach (not standard application)

### HiringPost:now hiring
- Signals: now hiring, looking for
- Contacts: hr@consultmpa.com
- Links: none found
- Snippet: MPA Healthcare Solutions - Chicago, IL - ONSITE * Software Engineer We are looking for a software engineer to join our small but growing development team. Our team has three primary responsibilities: 1) Supporting and maintaining existing c
- ACTION: draft PERSONALIZED outreach (not standard application)

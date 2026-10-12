# AutoApply SA — First-party recruitment prospects (2026-10-12)

**NON-SENDING RESEARCH ONLY. This file is not the authorized Notion Ready snapshot. Do not import to the sender, stage, or dispatch from this file.**

Live Notion collection: `collection://e22e718f-3141-41a9-aa5d-40fdc3aa98f9`.

At research time, the live Notion SQL query returned **0** records with `Send Status = Ready`. Supabase `autoapply_private.email_sending_control` was `paused=true`, reason `new-installation`. A subsequent Notion deduplication query was blocked by the Notion query quota; therefore **all these entries remain unapproved/unstaged**, even though the employer-published email addresses were observed on first-party websites.

## Candidate Yasmin Adam — sender apply@hsndm.tech

1. **Saudi Autism Society** — `jobs@saautism.org.sa`
   - Employer-published recruitment email on official jobs page: https://saautism.org.sa/1/وظائف-شاغرة/
   - Relevance: autism/psychology/support-related roles; exact vacancy, supervision eligibility and SCFHS requirements still need validation.
   - Status: Research only; Notion, entire send history, and provider-level suppression/dedup not cleared.

## Candidate Sultan Saud — sender apply1@hsndm.tech

2. **Arabian House Industries (AHI)** — `careers@ahi.com.sa`
   - Employer-published recruitment email: https://www.ahi.com.sa/careers.html
   - Relevance: process engineering, manufacturing operations, supply chain, quality systems. Page explicitly welcomes early-career applications; Riyadh roles.
   - Status: Research only; Notion, entire send history, and provider-level suppression/dedup not cleared.

3. **Food Sources Trading** — `careers@foodsources.com.sa`
   - Employer-published careers contact: https://www.foodsources.com.sa/en/contact
   - Relevance: supply chain and operations; no specific open position validated.
   - Status: Research only; Notion, entire send history, and provider-level suppression/dedup not cleared.

4. **PAC** — `hr@pac.com.sa`
   - Employer-published recruitment contact: https://pac.com.sa/en/careers
   - Relevance: operational services, quality, process improvement.
   - **Caution: the employer's careers page explicitly says there are no available positions currently**; deprioritize.
   - Status: Research only; Notion, entire send history, and provider-level suppression/dedup not cleared.

## Checks performed

- These exact four recipient emails were not found in the inspected GitHub `tracking.csv` (522 lines including header). This is not sufficient deduplication.
- No matches to these addresses / named employers were returned from the inspected private Supabase employer contacts query.
- The candidate/recipient dedup across all prior secure batches, Notion, historical records, and Brevo blocked/unsubscribed lists is **not complete**.
- No verification of mailbox deliverability, provider suppression, CV bytes, or up-to-date vacancy was performed.
- No emails were sent, staged, or queued from this research.

## Required before future outreach

Re-query live Notion and read exact records; finish cross-system candidate/company and exact-email dedup, including Brevo suppression and delivery events; check role/licensing fit; ensure PDF SHA-256 and candidate/sender pairing; obtain valid `Ready` Notion records only with evidence; confirm global sending pause is lifted through authorized operations; refresh the approved empty-or-eligible snapshot from Notion; use secure capped pacing and verify outcomes.

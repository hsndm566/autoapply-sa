# CAPTCHA-Resilient Application Model

## Executive position

A job-application platform cannot guarantee that no website will ever present a CAPTCHA. CAPTCHAs are designed specifically to distinguish automated activity from human activity. A dependable system therefore does **not** try to defeat them. It prevents them from becoming a throughput problem by moving most volume to channels that do not require interactive anti-bot challenges, detecting challenges before the final submission step, and reserving a small, evidence-backed manual lane for the exceptions.

The hCaptcha challenge at TSMG behaved as designed: after the approved CV upload and factual field completion, the challenge intercepted the final submit action. hCaptcha documents that a successful challenge adds a form token for the website to verify; that is a site-controlled human-verification step rather than an application field the platform can truthfully manufacture.[1]

## Current evidence

| Signal | Observed state | Operational implication |
|---|---:|---|
| Verified hCaptcha event | 1: TSMG Lever application | Lever is not a guaranteed straight-through source; use a CAPTCHA preflight and manual fallback lane. |
| Local browser timeout record | 1: Bayt | Do not make the user’s browser extension a critical path. |
| Active source registry | Greenhouse and Ashby | These are the primary portal candidates for controlled upload-proof testing. |
| Lead mix | 411 employer/other, 167 Bayt, 105 LinkedIn, 101 Indeed, 7 Ashby, 4 Greenhouse, 3 Lever | Most volume should be sourced and applied through direct employer channels, not social-network boards. |
| Gmail state | Cooldown after previous bounces | Direct-email volume remains capped and requires verified published application contacts plus Auditor approval. |

## Target source tiers

| Tier | Channel type | Automation treatment | Expected human work |
|---|---|---|---|
| A — Straight-through | Employer ATS forms that have a verified CV control, no login, no CAPTCHA, and a confirmed post-submit response | Highest priority; eligible for Auditor-gated submission | None once the adapter is proven. |
| B — Published direct application email | A current posting explicitly publishes an application address | Prepare and audit automatically; send only inside Gmail’s verified-contact and daily-volume limits | None unless a reply needs handling. |
| C — Profile-assisted portals | Bayt or similar portals with a maintained profile and simple questionnaire | Automate discovery and preflight; submit only after a source-specific proof pass | Occasional questionnaire review. |
| D — Manual exception | CAPTCHA, login, identity verification, unknown mandatory eligibility, or complex questionnaire | Stop before submit; retain all prepared factual data and a handoff link | One short human completion action. |
| E — Avoid/deprioritize | Repeated CAPTCHA, consistently expired pages, fake or unverified contact details, or role mismatch | Discover only; do not spend execution capacity | None. |

## Automation controls to implement

### 1. CAPTCHA preflight before form completion

Add a source adapter check immediately after navigation and before CV upload. It should detect visible `hcaptcha`, `recaptcha`, Cloudflare challenge pages, sign-in walls, and unsupported required questions. The adapter records the result as `captcha`, `login_required`, or `unsupported_question` and stops. This prevents investing a full application workflow into a portal that cannot finish autonomously.

### 2. Source reliability scoring

Maintain a rolling score per source and employer:

`straight_through_rate = confirmed_submissions / execution_attempts`

`challenge_rate = captcha_or_login_blocks / execution_attempts`

`factual_block_rate = factual_mismatch_or_ineligible / screened_leads`

The queue should prioritize high straight-through-rate sources and automatically demote a source for a cooling period when the challenge rate crosses a threshold. A practical starting rule is: after two CAPTCHA/login blockers in seven days for a source, move it to Tier D for 30 days until a manual review re-enables it.

### 3. Reusable source adapters rather than generic clicking

Each supported ATS needs its own tested adapter with four gates: a verified upload selector, exact required-field mapping, challenge preflight, and post-submit evidence capture. Greenhouse, Ashby, Lever, Bayt, and direct employer pages should never share a generic “click submit” routine. The TSMG result demonstrates why: the form’s CV upload worked, but an hCaptcha appeared only at final completion.

### 4. A separate manual-exception inbox

CAPTCHA-protected applications should become compact handoffs, not failures. Each handoff should contain the job URL, expiration date, approved CV, approved text, required answers, reason blocked, and a unique one-click status action: `submitted`, `not submitted`, `expired`, or `not eligible`. Once the human completes the challenge, the platform records only portal confirmation evidence before marking the application submitted.

### 5. Prioritize channels that avoid interactive challenges by design

The system should aim for a portfolio in which 60–70% of weekly applications come from proven Tier A ATS forms, 20–30% from verified published application contacts, and at most 10–15% from Tier C/D profile or challenge-prone portals. This keeps human effort bounded even when individual sites change their protections.

### 6. Candidate facts as a first-class eligibility gate

The MenaBev and GlobeMed examples were correctly excluded because their pages require Saudi nationality while the candidate record does not establish that fact. A structured candidate-facts profile should store verified work authorization, nationality when volunteered, relocation preference, graduation date, notice period, and salary preference. This reduces abandoned forms and prevents wasted challenge encounters.

### 7. Daily operational loop

1. Discover public jobs and normalize them into the database.
2. Apply employer, source, role-family, and factual-fit diversity rules.
3. Run source preflight without uploading a CV or filling fields.
4. Send Tier A forms to the Auditor and then execute with evidence capture.
5. Prepare Tier B emails but release them only inside Gmail reputation limits.
6. Place Tier D cases in the manual-exception inbox with all approved information ready.
7. Update source scores from real outcomes every day.

## What should not be used

The platform should not install GitHub CAPTCHA solvers, pay token-farm services, use stealth/browser-fingerprint evasion to defeat challenges, or claim a submission after only an upload or a button click. Those approaches are brittle and undermine the evidence trail. The goal is **high straight-through coverage**, not pretending that a human-verification layer does not exist.

## Immediate backlog

| Priority | Work item | Result |
|---|---|---|
| P0 | Add source-level CAPTCHA/login preflight to the managed-browser adapters | Stops applications before costly form fill on blocked sites. |
| P0 | Create a durable manual-exception endpoint and dashboard card | Turns each human step into a 1–2 minute task with evidence tracking. |
| P1 | Add source success/challenge/factual-block metrics to the queue | The queue self-optimizes toward sites that actually complete. |
| P1 | Prove one Greenhouse and one Ashby straight-through adapter end-to-end | Establishes reliable Tier A volume. |
| P1 | Record verified candidate eligibility facts | Avoids reopening Saudi-nationality or work-authorization gates repeatedly. |
| P2 | Build a daily source health report and auto-demotion rule | Prevents portal changes from silently degrading throughput. |

## References

[1] [hCaptcha Docs](https://docs.hcaptcha.com/)

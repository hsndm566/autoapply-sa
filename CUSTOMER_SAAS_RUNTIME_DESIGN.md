# AutoApply SA: Customer Runtime Design

## Purpose

A customer uploads a CV, receives a private campaign dashboard, and can see only that campaign's discovery, review, evidence, and application status. The system must remain useful after this engineering session ends; therefore the durable runtime is the Railway service, SQLite on the mounted volume, scheduled maintenance, the independent Auditor service, and explicitly configured third-party APIs. Manus is not a runtime dependency.

## What happens after a customer uploads a CV

The frontend sends a multipart request to `POST /v1/campaigns`. The service validates the required identity fields, validates the email, stores the CV under the configured durable storage directory, computes a SHA-256 hash, creates a campaign, and returns a private campaign access token. No email, browser submission, or external application is triggered by intake.

A background worker then performs safe discovery and drafting. It writes campaign jobs, events, and status transitions to SQLite. The frontend reads `GET /v1/campaigns/{campaign_id}` and `GET /v1/campaigns/{campaign_id}/events` with the campaign token. The stored `job_url` is the customer-facing application link. Evidence links are shown only when a verified evidence record exists; a log line is never presented as proof of submission.

The execution boundary is fail-closed. Current production configuration keeps external execution disabled until a source-specific CV-upload proof, Auditor approval, and post-submit evidence path exist. CAPTCHA, login requirements, unsupported mandatory questions, changed forms, and uncertain transport outcomes become review or blocked states rather than silent successes.

## Authentication and authorization

The current campaign boundary uses a per-campaign bearer token returned once at intake and stored only as a hash in SQLite. It is suitable for an early private link but is not yet a complete customer account system. Before selling this as a multi-customer product, add an identity layer with short-lived sessions, refresh/revocation, passwordless email or OAuth login, campaign ownership checks, rate limits, and an administrator role. Never put a Railway admin token in browser JavaScript.

## Referrals

A referral must be an explicit, authorized customer-provided record: referrer name, employer, contact method, permission status, and optional referral link. The engine may suggest an authorized referral to the customer or use it only where a form explicitly asks for it. It must not invent referrals, scrape private contact data, or claim a referral relationship that does not exist. The current repository does not yet contain a referral data model or workflow; that is a required product feature, not something to infer from a CV.

## Ledger and customer links

SQLite already provides the durable base ledger through `campaigns`, `campaign_jobs`, `campaign_events`, `action_outbox`, and `application_evidence`. Each row should expose the company, role, source, location, job URL, fit decision, Auditor state, submission state, evidence type, and timestamps. Google Sheets or Notion can be optional read-only mirrors, but the application database must remain the source of truth. A sync failure must never change an application status or create a duplicate submission.

## Per-customer CV processing

The profile extractor should produce a versioned fact record with provenance: each fact points to the CV page or section from which it was extracted. The Auditor should reject unsupported facts and require manual review for ambiguous fields. A new CV creates a new profile and campaign; it must not overwrite another customer's profile, CV, email, or application history.

## Runtime that does not depend on Manus

The long-running path is: frontend upload -> Railway API -> SQLite/volume -> safe discovery worker -> Auditor bridge -> source-specific adapter -> evidence record -> dashboard ledger. The worker uses ordinary Python processes and scheduled maintenance. If an external provider is unavailable, the system records a retryable or blocked state and continues operating for other campaigns. Manus may be used during development or for operator assistance, but it is not required to keep the service online.

The service must not rely on the local `autonomous_loop.py` as a production worker. That script is a legacy browser experiment and is separate from the governed Railway service. The Railway health output should be considered authoritative for production state, and `external_execution_enabled` must remain false until the governed path is proven.

## Dry-run results and fixes

The policy suite covered 14 synthetic customer/job variants. It initially found three faults: an unknown platform was implicitly approved, malformed fields could crash the evaluator, and a missing title could be approved. The evaluator now normalizes platform aliases and fails closed; all 14 policy scenarios pass.

The customer-journey suite covered 14 additional intake, authorization, job, evidence, contact, and outbox variants. It initially found five faults: empty or malformed campaign emails were accepted, malformed job URLs were accepted, empty evidence was accepted, and the evidence count was therefore incorrect. Database validation now rejects those inputs and links evidence only to the correct campaign. All 14 journey scenarios pass.

The repository regression suite completed with 81 tests passing. These are offline or controlled tests; they do not prove that a live third-party portal will accept a submission, that Gmail confirmations will arrive, or that any paid browser provider will remain available.

## Productization gates before accepting customer money

The next implementation gates are customer authentication, CV fact extraction with provenance, referral records, a frontend campaign dashboard, a durable ledger-to-frontend API, optional Google Sheets/Notion mirroring, a per-customer queue, source-specific upload proof, and a controlled single-application canary. Only after those gates pass should external submission be enabled for a customer campaign.

# AutoApply SA — Multi-Source Sourcing and Verification Plan

## Objective

Build a source-diverse, low-cost job inventory that works with different CVs **without pretending that every job is automatically applicable**. The system must discover broadly, verify whether each job has a real candidate path, match jobs to a truthful candidate profile, and send only packages approved by the existing Auditor.

> **Process guarantee, not vacancy guarantee:** The system will keep searching across approved role lanes, locations, employer boards, and outreach contacts until it reaches the target inventory or reports the honest shortfall. It must never promise that every CV has 50–100 appropriate live openings at every moment.

## 1. Truthful Job States

Every job must move through the following states. Only the final state counts as a successful portal application.

| State | Meaning | May spend AI tokens? | May send or submit? |
| --- | --- | ---: | ---: |
| `discovered` | A source returned a raw listing. | No | No |
| `normalized` | Required fields were mapped into the shared job schema. | No | No |
| `deduplicated` | The company, role, source URL, and posting ID are not already active. | No | No |
| `matched` | The title, location, seniority, and candidate facts meet the configured threshold. | Minimal | No |
| `path_verified` | The candidate-facing route was checked and classified. | No | No |
| `drafted` | A tailored package exists. | Yes | No |
| `audit_approved` | The Auditor approved the exact package and CV artifact. | Yes | No |
| `submitted_verified` | A verified success indicator was captured after submission. | No | Yes—already completed |
| `needs_review` / `blocked` | The path has a blocker, unsupported question, login, or missing evidence. | No | No |

## 2. Source Portfolio

Source diversity is the control that prevents the engine repeatedly targeting Anthropic, GitLab, and other familiar large employers.

| Tier | Source family | Primary use | Submission handling | Cost policy |
| --- | --- | --- | --- | --- |
| A | Greenhouse | Public job discovery, job detail, field discovery | Candidate-hosted form adapter after verified resume upload | Default daily source |
| A | Lever | Public job discovery, `applyUrl`, location/team filters | Candidate-hosted form adapter after verification | Default daily source |
| A | Ashby | Public listing and `applyUrl` discovery | Candidate-hosted form adapter after verification | Default daily source |
| B | Workday, SmartRecruiters, Workable, Recruitee, Personio, Teamtailor, Breezy, BambooHR, iCIMS, SuccessFactors, Oracle | Employer-board discovery and source-specific listing adapters | Only after source-specific candidate-flow test | Add one adapter at a time |
| C | Direct employer/recruiter contacts | Verified targeted outreach | Separate audited email lane | Existing 417/500-contact asset |
| D | LinkedIn and Bayt via Apify | Discover companies, role vocabulary, and missing sectors | Never the sole source of truth | Run only a limited discovery sweep |

Greenhouse, Lever, and Ashby should be the first implementation set because their public data exposes job URLs and structured listing data. Public listing data is not permission to use a private application API; the candidate-facing hosted form remains the execution target unless the employer explicitly provides a candidate submission mechanism.

## 3. Shared Job Schema

Hermes must normalize every source into one record before scoring or drafting.

```json
{
  "source": "greenhouse",
  "employer_key": "company-domain-or-board-token",
  "posting_id": "source-stable-id",
  "company": "Example Company",
  "title": "Business Systems Analyst",
  "location": "Riyadh, Saudi Arabia",
  "remote": false,
  "employment_type": "FullTime",
  "posted_at": "2026-08-12T00:00:00Z",
  "job_url": "https://...",
  "apply_url": "https://...",
  "description": "...",
  "application_mode": "unknown",
  "required_fields": [],
  "fetched_at": "2026-08-12T00:00:00Z"
}
```

Deduplicate on `source + posting_id` first, then use a softer company/title/location fingerprint to catch cross-posts. Preserve all source URLs as evidence; never replace a direct employer URL with a LinkedIn or Bayt redirect.

## 4. Candidate Profile and Matching

For each CV, extract a factual candidate profile once and make it the only source used for matching and drafting. It should contain target titles, title synonyms, skills, seniority, city/remote preference, language, work authorization facts, and explicit exclusions. Do not infer missing qualifications.

Use a simple score before any drafting:

| Component | Suggested points | Rule |
| --- | ---: | --- |
| Target-role match | 0–35 | Exact title and approved adjacent title mappings score highest. |
| Required-skill overlap | 0–25 | Use only skills demonstrably present in the CV. |
| Location/workplace fit | 0–15 | Saudi city, remote, hybrid, and relocation rules come from the campaign brief. |
| Seniority fit | 0–15 | Do not apply upward into unsubstantiated seniority. |
| Freshness and application readiness | 0–10 | Prefer recent jobs with a verified direct route. |

Draft only jobs above the campaign threshold. The lower-scoring inventory can still appear in a “possible matches” view, but it must not consume browser or AI resources.

## 5. Path Verifier

The Path Verifier is the missing layer between sourcing and the Auditor. It establishes whether the job is actually eligible for automation.

| Classification | Requirement | Next action |
| --- | --- | --- |
| `direct_email` | Verified employer/recruiter address and a relevant role or explicitly labelled speculative outreach | Build audited email package. |
| `portal_file_upload` | Candidate form opens, a resume file input is present, required fields are known, and no unsupported blocker appears | Eligible for the source-specific submit adapter. |
| `portal_complex` | Candidate form has additional questions, consent decisions, or conditional steps the adapter does not support | Hold for manual review or adapter expansion. |
| `login_or_captcha` | Login, CAPTCHA, or other anti-bot control is present | Record and stop; do not bypass controls. |
| `expired_or_duplicate` | Listing is closed or previously attempted within the policy window | Drop. |

The verifier performs read-only checks first. It must not create a session, submit a form, or spend Browserbase capacity until the job is already matched and `portal_file_upload` is plausible.

## 6. Employer and Source Diversity Rules

The source registry must enforce diversity before packages reach the Drafter.

| Rule | Default |
| --- | --- |
| Maximum verified options from one employer | 2 per campaign per 30 days |
| Maximum verified options from one ATS source | 35% of a campaign inventory |
| Maximum large/employer watchlist concentration | 10% of a campaign inventory |
| Minimum employer count before 50 options are declared | 20 employers |
| Minimum source-family count before 50 options are declared | 4 source families |
| Duplicate/repost window | 90 days by employer + role + applicant |
| Apify budget rule | Weekly discovery only; no repeated extraction of already-known boards |

Anthropic, GitLab, and other heavily repeated companies should be placed in a configurable `employer_cap` list. Their jobs remain eligible only if they are strong exact matches and the campaign has not reached the cap.

## 7. Low-Cost Discovery Loop

1. Maintain a `source_registry` of employers, ATS type, board slug, careers URL, country/sector tags, and last-successful-refresh time.
2. Refresh Tier A boards daily using ordinary HTTP requests and source-specific pacing.
3. Refresh Tier B boards on a rotating schedule, beginning with the adapters that return stable structured data.
4. Run Apify once or twice per week only to identify new employers, role synonyms, and missing Saudi sectors.
5. Resolve discovered employer career URLs into a registry entry. From then on, refresh that employer directly rather than paying to rediscover it.
6. Normalize, deduplicate, score, and path-verify before any LLM call.
7. Feed only the top verified options to the Drafter, Auditor, and dispatcher.

## 8. Implementation Sequence

### Phase A — Foundation

1. Create `source_registry.json` or a database table with source, employer, board identifier, careers URL, tags, status, and last refresh.
2. Replace the current fixed list of high-profile Greenhouse boards with registry-driven selection.
3. Implement normalized records and database deduplication for every adapter.
4. Add source and employer caps before the drafting call.

### Phase B — Free Structured Sources

1. Harden Greenhouse path discovery and build a verified hosted-form upload adapter.
2. Add Lever discovery with public `applyUrl` retrieval and hosted-form verification.
3. Add Ashby discovery with public job-board and `applyUrl` retrieval.
4. Add one Tier B source at a time. Every adapter needs saved fixtures, an offline unit test, and a read-only live canary before it can send candidates to the dispatcher.

### Phase C — Proof and Operations

1. Capture post-submit proof: timestamp, final URL, confirmation text, application ID if exposed, source, and CV hash.
2. Create an inventory dashboard that separates leads, verified options, audit approvals, verified submissions, outreach, blockers, and source health.
3. Run nightly **read-only** source canaries; a board that changes layout becomes `source_degraded`, not an excuse to guess or bypass.
4. Make live submission a per-source feature flag enabled only after a source-specific E2E test proves CV upload and confirmation capture.

## 9. Open-Source References to Evaluate, Not Blindly Copy

| Resource | Useful lesson | Caution |
| --- | --- | --- |
| `kalil0321/ats-scrapers` | Normalized schema, broad source adapters, retries, error mapping, and opt-in live canaries | Evaluate the dependency version, source terms, and individual adapters before production use. |
| `plibither8/jobber` | Minimal board-adapter interface across five ATS platforms | Suitable reference pattern, not a complete production pipeline. |
| `Feashliaa/job-board-aggregator` | Registry, rate-aware fetches, dedupe, pruning, source trends, and anomaly alerts | Its curated datasets are non-commercial; do not import them into a commercial product without permission. |
| `billyweinberger/job-scraping-app` | Clean separation between fetchers, normalizer, ranker, reporting, and optional AI | Treat it as an architecture reference. |

## 10. Hermes Acceptance Criteria

Hermes must not call this complete until all conditions below are true:

1. The source registry replaces the hard-coded repeat-company list.
2. The system can source Greenhouse, Lever, and Ashby listings into the shared schema without Apify.
3. A candidate campaign honors employer, ATS, and repost diversity caps.
4. A job receives `portal_file_upload` only after the resume input and required-field model are positively verified.
5. Every submission source retains the existing `audit_application(..., require_ai_review=True)` and `assert_execution_allowed(...)` gates.
6. Every live source adapter has offline fixtures, a read-only live canary, and a post-submit proof test.
7. A blocked or insufficient-inventory campaign reports the truth; it never fabricates a 50–100 job inventory.

## References

[1] Greenhouse Job Board API — https://developers.greenhouse.io/job-board.html

[2] Lever Postings API — https://github.com/lever/postings-api

[3] Ashby Job Postings API — https://developers.ashbyhq.com/docs/public-job-posting-api

[4] SmartRecruiters Posting API — https://developers.smartrecruiters.com/docs/posting-api

[5] ats-scrapers — https://github.com/kalil0321/ats-scrapers

[6] jobber — https://github.com/plibither8/jobber

[7] Job Board Aggregator — https://github.com/Feashliaa/job-board-aggregator

[8] Job Scraping App — https://github.com/billyweinberger/job-scraping-app

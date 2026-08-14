# AutoApply SA System Guide

> **Purpose.** AutoApply SA is a Saudi Arabia-focused campaign system for receiving a candidate brief and CV, maintaining a durable campaign record, discovering roles in a controlled read-only mode, and presenting honest campaign status. It is not currently an autonomous live-application or bulk-email system.

## 1. Current system boundary

| Layer | Current implementation | Verified address or source | Operational state |
| --- | --- | --- | --- |
| Public site | React 19 + TypeScript + Vite static frontend | [hsndm.tech](https://hsndm.tech), GitHub Pages with `CNAME` | Live static site |
| Frontend source | Manus-managed full-stack project mirrored to Pages | `hsndm566/hsndm.tech` | Published through the static release script |
| Campaign API | Python `service.py` using `ThreadingHTTPServer` | `https://autoapply-sa-production.up.railway.app` | Railway primary |
| Health check | `GET /healthz` | `https://autoapply-sa-production.up.railway.app/healthz` | Public and observed healthy on 2026-08-14 |
| Campaign database | SQLite through `db.py` | Railway volume, expected at `/data/autoapply/autoapply.db` | Durable when the Railway volume remains attached |
| Cloud backup | Azure preparation only | No production Azure resource or URL exists | Not provisioned; Entra GitHub OIDC remains blocked |
| Browser automation | Browser handoff / source-specific proof code | Not a runtime requirement for the public site | Portal submission remains disabled |
| Local operator | Hermes on the owner’s computer | Local terminal workflow | Optional; no remote connector is configured here |

The Railway service is the current operational backend. The task brief reports a Railway spend of **$4.81**; this figure is not independently verified by this repository and must be checked in the Railway billing view before any decision is made from it.

## 2. What works and what does not

| Capability | Current state | Important limit |
| --- | --- | --- |
| Campaign creation | Available through `POST /v1/campaigns` | A created campaign does not send applications.
| Candidate status and event feed | Available with `X-Campaign-Token` | Candidate access is per campaign token.
| Evidence-aware candidate dashboard | Implemented in the frontend at `/campaign/{campaign_id}#access={token}` | Requires the Railway summary response and a real campaign link for live validation.
| Public role discovery | Enabled in controlled read-only mode | It does not apply to jobs.
| Audited email preparation | Built | SMTP delivery stays disabled until explicitly configured.
| Portal upload-proof adapter | Built and offline-tested | Live portal submission stays disabled.
| GitHub Pages site | Published static mirror | Dynamic campaign URLs rely on the Pages SPA fallback.
| Azure fallback | Documentation and inert infrastructure definitions prepared | No authenticated Azure deployment identity is available.

The public Railway health response observed on 2026-08-14 reported **three `active_readonly` campaigns**, no recorded submitted application metrics, and external execution disabled. Client names, email addresses, CVs, and access tokens are intentionally not stored in this guide or in public GitHub documentation.

## 3. Database tables

The SQLite schema in [`db.py`](./db.py) currently defines these 16 tables:

| # | Table | Purpose |
| ---: | --- | --- |
| 1 | `discovered_jobs` | Raw read-only job discovery records. |
| 2 | `applications` | Legacy application workflow records. |
| 3 | `browser_handoff_attempts` | Browser handoff observations only. |
| 4 | `dead_letter` | Failed or blocked work requiring review. |
| 5 | `run_flags` | Kill-switch and execution control state. |
| 6 | `run_budget` | Bounded operational budget state. |
| 7 | `campaigns` | Candidate campaign metadata and token hash. |
| 8 | `campaign_events` | Campaign activity timeline. |
| 9 | `campaign_jobs` | Candidate-specific discovered opportunities. |
| 10 | `action_outbox` | Controlled, idempotent future actions. |
| 11 | `outreach_contacts` | Verified, suppressed, or opted-out contact records. |
| 12 | `campaign_contact_attempts` | Per-campaign contact reservation state. |
| 13 | `application_evidence` | Evidence records used for truthful application totals. |
| 14 | `source_health` | Source availability and observed failures. |
| 15 | `portal_probe_runs` | Read-only portal-probe evidence. |
| 16 | `service_health` | Runtime health checks. |

## 4. Execution flags and required safe state

| Control | Expected production value | Effect |
| --- | --- | --- |
| `ALLOW_LEGACY_EXTERNAL_EXECUTION` | `false` | Blocks the legacy execution route. |
| `ALLOW_GREENHOUSE_LIVE_SUBMISSION` | `false` | Blocks live portal submission. |
| `EMAIL_OUTREACH_ENABLED` | `false` until a controlled approval | Blocks SMTP sends while retaining safe queued work. |
| `CORS_ORIGIN` | `https://hsndm.tech` | Restricts browser API access to the production site. |
| `DB_PATH` | `/data/autoapply/autoapply.db` | Points the service to the Railway volume. |
| `CV_STORAGE_DIR` | `/data/autoapply/cv` | Holds uploaded CV artifacts on the Railway volume. |

Never add secret values, live access tokens, candidate CV content, or client email addresses to Git, generated documentation, browser URLs without a fragment, or public site configuration.

## 5. API reference

| Method and route | Authentication | Purpose |
| --- | --- | --- |
| `GET /healthz`, `GET /status` | None | Health, aggregate metrics, source and service checks. |
| `GET /v1/portal-queues/bayt` | None | Read-only Bayt handoff queue summary. |
| `GET /v1/portal-queues/diversified` | None | Read-only diversified queue summary. |
| `POST /v1/campaigns` | None; CORS-limited | Create a campaign and return a one-time campaign access token. |
| `GET /v1/campaigns/{id}` | `X-Campaign-Token` | Campaign summary, evidence count, evidence-linked company records, and SMTP-acceptance count. |
| `GET /v1/campaigns/{id}/events` | `X-Campaign-Token` | Campaign activity feed. Activity is not submission proof. |
| `POST /v1/campaigns/{id}/start` | `X-Campaign-Token` | Enable safe discovery and drafting only. |
| `POST /v1/campaigns/{id}/pause` | `X-Campaign-Token` | Pause future campaign work. |
| `POST /v1/admin/portal-handoffs/outcomes` | `X-Job-Import-Token` | Record browser handoff outcome. |
| `POST /v1/admin/auditor/review` | `X-Job-Import-Token` | Request an auditor review. |
| `POST /v1/admin/auditor/self-test` | `X-Job-Import-Token` | Verify reviewer connectivity. |
| `POST /v1/admin/jobs/import` | `X-Job-Import-Token` | Import discovered jobs. |
| `POST /v1/admin/contacts/import` | `X-Admin-Token` | Import verified contact data. |
| `POST /run`, `POST /kill`, `POST /resume` | `X-Admin-Token` | Legacy and operational controls; do not expose to candidates. |

## 6. Campaign operation, end to end

1. Receive a candidate’s explicit campaign brief and CV through the authenticated campaign intake path.
2. Store only the campaign data and CV artifact required by the service on the Railway volume.
3. Give the candidate their private status link in the form `https://hsndm.tech/campaign/{campaign_id}#access={token}`. The fragment prevents the browser from sending the token in the HTTP request URL.
4. The dashboard requests the existing campaign summary and event routes with `X-Campaign-Token`; it counts only `application_evidence` as application proof.
5. Start a campaign only after confirming the candidate’s intent. The current `active_readonly` mode performs discovery and drafting only.
6. Do not enable email or portal execution until the verified contact source, independent Auditor, and source-specific upload proof requirements in [`OPERATIONS_HANDOFF.md`](./OPERATIONS_HANDOFF.md) are complete.

## 7. Add a new client safely

Do not create a client by editing SQLite manually. Use the campaign intake API, retain the returned access token only in an approved private channel, and do not put it into a GitHub issue, public chat, or a static link query parameter. Before start, confirm the candidate’s role, city, industry, and consent. Before any outbound delivery, complete the controls in the operations handoff and obtain the required operational approval.

## 8. Configuration and third-party services

| File or service | Function | Notes |
| --- | --- | --- |
| [`service.py`](./service.py) | HTTP service, CORS, endpoints, scheduler boot | Entry point on Railway. |
| [`db.py`](./db.py) | SQLite schema and durable operations | Treat as the authoritative campaign data contract. |
| [`railway.json`](./railway.json) | Railway build/start/health policy | Nixpacks, `python service.py`, `/healthz`. |
| [`Procfile`](./Procfile) | Alternate process declaration | `web: python service.py`. |
| [`.env.example`](./.env.example) | Variable-name reference only | Never commit populated credentials. |
| [`OPERATIONS_HANDOFF.md`](./OPERATIONS_HANDOFF.md) | Production activation sequence | Primary runbook for deliberate operational changes. |
| Railway | Primary compute and volume | Account credentials live outside the repository. |
| GitHub Pages | Static website hosting | The website is not a server-side proxy. |
| Manus | Development and controlled agent tooling | Not a runtime dependency of `service.py`. |
| DeepSeek | Intended independent Auditor provider | Actual provider key/configuration must be verified in Railway. |
| Groq | Task-brief-reported drafting provider | Not verified from the live Railway variable set. |
| Accio | Task-brief-reported email sourcing service | Not verified from the current repository configuration. |
| Anchor Browser | Task-brief-reported cloud browser | Not verified as an active runtime dependency in the current service. |
| Azure | Backup target | No live backup URL exists because no production resource has been provisioned. |

## 9. Logs, health, and handoff

Use the Railway dashboard or authorized Railway API connector for deployment logs and variable names. Begin every incident with `GET /healthz`, then inspect `service_health`, `source_health`, campaign events, and the action outbox through an authorized operational channel. Do not use candidate dashboard data to diagnose another candidate’s campaign.

For a new operator, read this file, then [`OPERATIONS_HANDOFF.md`](./OPERATIONS_HANDOFF.md), [`MANUS_CONTEXT.md`](./MANUS_CONTEXT.md), and [`STATUS.md`](./STATUS.md). Confirm the health endpoint, inspect only non-secret deployment metadata, and preserve the fail-closed flags before touching any operational configuration.

## References

[1] [`service.py`](./service.py) — public endpoint and authorization implementation.

[2] [`db.py`](./db.py) — SQLite schema, campaign authorization, and evidence-summary behavior.

[3] [`OPERATIONS_HANDOFF.md`](./OPERATIONS_HANDOFF.md) — verified operating state and activation gates.

[4] [`railway.json`](./railway.json) — Railway deployment contract.

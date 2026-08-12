# Portal Sentinel Deployment Evidence

**Deployment date:** 12 August 2026

## Release scope

This release adds a **read-only Portal Sentinel** to AutoApply SA. The Sentinel performs bounded HTTP `GET` observations against public, already-discovered Greenhouse/Ashby/Lever job URLs. It stores a privacy-minimized structural fingerprint and detects change, blockers, and availability errors. It has no browser driver, CV path, field-fill routine, outbox writer, email sender, or submit method.

| Component | Production result |
| --- | --- |
| Backend commit | `5482521` — Portal Sentinel, evidence schema, worker integration, research and architecture documentation |
| Accounting correction | `b230635` — configured sources no longer count as failed health checks |
| Railway service | Deployed successfully; `/healthz` returned HTTP 200 |
| Website commit | `461ebb7` in `hsndm566/hsndm.tech` — published dashboard monitoring indicator |
| Frontend source commit | `53f820e` in `hsndm566/hsndm.tech2` — source of the published dashboard update |
| Full backend regression suite | **61 tests passed** |
| Frontend production build | Passed; public `thank-you` bundle contains the Portal Sentinel status indicator |

## Production observation

The deployed Sentinel executed its bounded read-only pass. The health endpoint reported `portal_sentinel: healthy`, `probed=1`, `skipped=2`, and `external_execution=disabled`. Its Greenhouse observation returned `PORTAL_BLOCKER_DETECTED` and the source was correctly marked `blocked` rather than being silently treated as viable. No browser was opened, no CV was uploaded, no email was sent, and no application was submitted.

> A `blocked` observation is a successful safety outcome. It means the system detected a form-level anti-automation/login-style marker and held the source rather than guessing, bypassing, or reporting a false application success.

## Current operating state

| Capability | State |
| --- | --- |
| Customer CV campaign intake | Live |
| Durable campaign event/status dashboard | Live |
| Greenhouse/Ashby public discovery | Live and read-only |
| Portal structural monitoring | Live and read-only, six-hour default cadence per source |
| Portal upload proof adapter | Offline-tested; live switch remains false |
| Email contact import and audited dispatcher | Built; delivery remains disabled pending credentials and a verified list |
| Legacy external executor | Disabled |
| Auditor gate | Active and fail-closed |

## Deliberate non-results

This release did not send a test application without a CV, did not contact a random company, and did not enable portal or Gmail delivery. Those actions would violate the immutable package, evidence, and Auditor requirements. The objective of this release is to make portal drift observable and automatically held before an unsafe execution attempt can occur.

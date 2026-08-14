# AutoApply SA Status

**Status date:** 2026-08-14

## Completed in this finalization pass

| Area | Completion |
| --- | --- |
| Mobile background video | Enabled the managed muted loop for supported phones and desktops, with a reduced-motion poster fallback and no controls or pointer interaction. |
| See It Work section | Replaced the empty video-ready branch with the existing approved managed loop, a static poster, and an explicit AutoApply SA caption. |
| Homepage content pass | Confirmed the approved English hero, subheading, engine labels, intake wording, Saudi-only language, reduced redundant explanations, and removal of the unsupported Julie copilot claim. |
| Private campaign dashboard | Added `/campaign/{campaign_id}#access={token}`. It calls only the existing Railway summary and events routes, sends the bearer token as `X-Campaign-Token`, applies `noindex`, and distinguishes evidence from operational activity. |
| Evidence-aware API summary | Extended the existing authenticated campaign summary response with `email_send_count`, `last_application_at`, and evidence-linked company rows. No new API endpoint was added and evidence values are withheld. |
| Tests | The backend campaign-platform test passed with the evidence-summary case. The frontend test suite, TypeScript check, and production build passed with 49 frontend tests. |
| Handoff records | Added `SYSTEM.md`, `MANUS_CONTEXT.md`, and this file without credentials, customer records, CV content, or access tokens. |

## Still pending

| Item | Why it remains pending | First safe action |
| --- | --- | --- |
| Push and verify backend release | The source change must reach Railway through the normal `main` deployment. | Push the verified `autoapply-sa` commit, inspect Railway deployment logs, and confirm `/healthz`. |
| Test a real candidate dashboard link | No authorized campaign access token was provided to this session. | Open one candidate-provided link in a browser and confirm summary, evidence, and events render only for that campaign. |
| Verify frontend CORS end to end | Sandbox TLS could not run a direct Railway request, though the owner browser loaded `/healthz`. | Open `hsndm.tech` in a normal browser and use an approved campaign link; inspect only browser console/network results, never log a token. |
| Candidate company list completeness | Only evidence rows linked to `campaign_jobs` can show companies. | Ensure new proof-producing workers carry `campaign_job_id`. |
| Candidate email-detail log | The live API records SMTP-acceptance evidence but does not expose a recipient-level `email_send_log.csv`. | If recipient-level reporting is truly required, design a private per-campaign summary field with privacy review; do not expose contacts by default. |
| Azure migration | Azure OIDC identity is blocked by missing Entra federated credential. | Add the documented GitHub Actions federated credential, then run the read-only inventory. |
| External email and portal application delivery | Deliberately disabled. | Follow the gated activation sequence in `OPERATIONS_HANDOFF.md`; do not enable flags opportunistically. |

## First actions tomorrow

1. Verify that the two repository commits and their deployments reached `hsndm.tech` and the Railway service.
2. Use an authorized real campaign link to validate the private dashboard in the production browser.
3. Confirm CORS behaviour on the production origin and that the token remains in the URL fragment rather than the query string.
4. Review whether the candidate-facing email count is sufficient or whether a privacy-reviewed recipient record is necessary.
5. Resolve Azure identity only after confirming the federated credential setup; do not create cloud resources before the read-only check passes.

## Cost and verification note

The task brief reported Railway spend of **$4.81**. This repository cannot verify live billing, so treat it as an operator-provided reference and check Railway billing directly before acting on it.

## Issues observed during verification

| Issue | Impact | Current resolution |
| --- | --- | --- |
| Sandbox TLS requests to Railway failed with `SSL_ERROR_SYSCALL`. | Prevented a direct shell-level CORS check. | The connected browser loaded the production health endpoint successfully; use authorized browser or Railway tooling for live validation. |
| GitHub Pages is static. | Dynamic campaign paths rely on its SPA fallback. | Keep dashboard routes client-side and test direct links after every static deploy. |
| Production token test unavailable. | Live campaign dashboard data could not be viewed in this session. | Keep the UI honest and complete the authorized browser test before calling the dashboard fully production-verified. |
| Azure OIDC is incomplete. | Azure remains a prepared fallback, not a running deployment. | Add the missing Entra federated identity credential first. |

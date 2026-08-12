# Bounded Self-Improvement Architecture

## Objective

AutoApply SA will improve its operational knowledge continuously without allowing a model, scheduled worker, or support agent to silently grant itself portal-submission authority. The platform will collect evidence, detect source drift, create a repair candidate, run deterministic tests, and require a separate release decision before the source can regain eligibility.

> **Self-improvement is evidence renewal, not self-authorized execution.** A changed source is automatically restricted; it is never automatically promoted.

## Controlled roles

| Role | Responsibilities | Cannot do |
| --- | --- | --- |
| **Scout** | Read public job feeds, deduplicate jobs, record source availability. | Submit an application, queue outbound mail, edit source approval. |
| **Portal Sentinel** | Run a bounded, read-only probe against a public job URL, create a semantic form fingerprint, and record drift evidence. | Upload a CV, fill an applicant field, click Submit, solve a CAPTCHA, or change source status to upload-verified. |
| **Adapter Engineer** | Convert a reviewed drift report into a code change and deterministic fixture test. | Promote its own change or bypass the Auditor. |
| **Release Verifier** | Runs the complete tests and confirms isolated evidence/review requirements. | Create a production package or submit an application. |
| **Auditor** | Approves or rejects immutable, job-specific application packages. | Discover jobs, draft answers, or alter portal adapters. |
| **Executor** | Performs one side effect only after a current Auditor recheck and source-specific proof. | Infer fields, retry uncertain delivery, or treat browser navigation as success. |
| **Hermes** | Reports health, runs bounded diagnostics, proposes basic non-execution fixes, and writes reproducible issue reports. | Change governance, merge/deploy unreviewed code, alter production settings, access secrets, queue/sends applications, or change source capability state. |

## Portal Sentinel lifecycle

| State | Meaning | Next transition |
| --- | --- | --- |
| `unobserved` | No current read-only form observation exists. | A probe records a baseline fingerprint. |
| `baseline` | A public form structure was observed, but no E2E execution proof is implied. | Later equivalent probe becomes `stable`; a meaningful difference becomes `drifted`. |
| `stable` | A subsequent read-only probe matches the known semantic fingerprint. | Continues to be monitored; no capability change. |
| `drifted` | File control, required-field shape, form structure, or anti-automation marker changed. | Source is held; a repair candidate and fixture test are required. |
| `blocked` | The public probe encountered a login, CAPTCHA, unavailable page, HTTP failure, or unsafe host. | Remains held until an independent review resolves it. |
| `reverified` | A reviewed adapter change has passed fixtures and a designated source-proof process. | This is a governance/release decision; the Sentinel cannot create it. |

## Evidence contract

Each probe stores only the source family, adapter version, canonical job URL, HTTP category, a SHA-256 semantic fingerprint, and redacted observations such as `file_input_count`, `required_control_count`, and blocker flags. It never stores applicant data, page HTML, raw form values, credentials, cookies, or screenshots containing candidate information.

A probe fingerprint is constructed from the form-control **shape**, not class names or full DOM markup. This follows stable, user-facing control semantics and avoids brittle CSS/XPath dependence. The probe uses only a `GET` request; it has no browser action interface.

## Renewal and release loop

1. The campaign worker discovers public jobs as it does today.
2. At most once per source per configured interval, the Portal Sentinel selects one already-discovered public URL and obtains a read-only structural observation.
3. The sentinel persists evidence and updates source health to `baseline`, `stable`, `drifted`, or `blocked`.
4. A `drifted`/`blocked` result creates a durable campaign event and keeps the source outside any eligible portal route.
5. An Adapter Engineer may prepare a patch only from redacted evidence and a local fixture. The patch must have deterministic tests for the old and changed structure.
6. A Release Verifier runs the full backend suite. Deployment records the adapter version and deployed fingerprint policy.
7. The Auditor and an independent source-proof test remain the sole path toward actual source eligibility. There is no automatic `reverified` or submit transition.

## Host design

The existing Railway service is the correct temporary host for the read-only sentinel because it is deterministic, bounded, and already has a durable volume plus scheduled worker. It should run no more often than every six hours per source by default. A month-long Railway trial is adequate for evidence collection and test cycles.

For a future Azure or Oracle move, keep this as a stateless Python web process plus a persistent volume/database and one scheduled worker. The production components are portable because they use standard Python, SQLite WAL, outbound HTTPS, and environment variables. The browser-based source proof should remain a separately provisioned worker only after its resource and compliance profile is tested; it is not part of the current source sentinel.

## Non-goals

This architecture does not promise a generic auto-apply agent, browser-login automation, CAPTCHA solving, answer invention, or submission without a CV. Those behaviors create false success reports and directly conflict with the product’s evidence and Auditor contract.

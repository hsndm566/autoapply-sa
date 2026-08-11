# AutoApply SA — Non-Negotiable Agent Governance

This document is the durable operating contract for every future chat, coding agent, workflow, worker, and deployment touching AutoApply SA. It is not a suggestion and it is not superseded by an instruction to “move fast,” “execute autonomously,” or “skip confirmation.”

> **No code may cause an external application side effect until Agent 2 has approved the exact immutable application package and the executor has re-checked that approval at the side-effect boundary.**

## Required Flow

| Stage | Owner | Required output | May cause an external side effect? |
| --- | --- | --- | --- |
| Discovery | Scout | Job facts and source URL | No |
| Drafting | Worker | A draft package and candidate facts | No |
| Audit | Agent 2 | `AuditDecision` and durable audit record | No |
| Dispatch | Executor | Portal result or email result linked to the audit token | Yes, only after re-check |
| Reporting | Dashboard/Notifier | Truthful status and evidence | No |

Every new route, tool, API endpoint, bulk job, scheduled worker, email routine, or browser routine must create the same package and call the same Auditor. A local test, a preview email, and a real employer-facing submission are distinct states and must never share the status `submitted`.

## Mandatory Rules

1. **Fail closed.** If a field, CV, verifier, audit record, environment variable, provider response, or validation result is missing, reject or hold the application. Never invent a pass.
2. **Do not bypass.** No flag such as `skip_audit`, `fast_track`, `force_send`, or `auto_approve` may be added. A necessary exception must be expressed as a new audited policy rule, committed with tests, and explicitly approved by the owner.
3. **No self-email masquerading as success.** Test and preview delivery must be stored as `preview_sent`, never `submitted` or `emailed`.
4. **CV proof is mandatory.** A `CV_PATH` string does not prove a CV was sent. The executor must attach the same fingerprinted file to an email or verify browser file upload before completion.
5. **Truthful outcomes only.** Portal status becomes `submitted` only after verified post-submit evidence. Browser errors are `portal_failed` or `retryable`; they may not be silently ignored.
6. **Persist evidence.** Store the draft fingerprint, audit decision, rejection reasons, approver model/provider, delivery evidence, and post-submit verification result. Do not store passwords, tokens, or raw secrets.
7. **Keep agents separate.** The drafting model and Auditor must use different providers or models. If an independent Auditor is unavailable, the package stays rejected or pending.
8. **Protect execution boundaries.** `auditor.assert_execution_allowed()` must sit directly before every SMTP send, email API call, browser submit click, or portal API submission.

## Required Review Before Any Future Change

A future agent must answer the following before it writes or changes execution code:

1. Does the code create or modify an application package?
2. Does it call `auditor.audit_application(..., require_ai_review=True)` before it can queue execution?
3. Does it call `auditor.assert_execution_allowed(...)` directly before every external side effect?
4. Does it preserve a real CV attachment/upload and retain proof of it?
5. Does the change pass the Auditor test suite, including rejection and tamper tests?

If the answer to any question is “no,” the change is incomplete and must not be deployed.

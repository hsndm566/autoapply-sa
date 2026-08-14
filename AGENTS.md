# AutoApply SA — Mandatory Agent Rules

> **Read this file before changing, testing, or operating the application pipeline. These rules are non-negotiable. The runtime code in `auditor.py` and `email_dispatcher.py` is the final enforcement authority.**

## Outbound Email Applications

1. **Never send an application email directly through SMTP, Gmail, a browser, or any custom script.** Every email application must use `email_dispatcher.queue_audited_email_application()` and `email_dispatcher.dispatch_one()` / `dispatch_pending()`.
2. **Every outgoing application email must contain exactly one CV PDF attachment.** The attachment must have a `.pdf` filename, MIME type `application/pdf`, a valid `%PDF-` signature, and a valid PDF ending marker.
3. **The bytes attached to the email must exactly match the CV artifact that was approved by the Auditor.** Do not substitute, regenerate, rename, or modify the CV after approval.
4. **If the CV is missing, unreadable, malformed, too large, non-PDF, duplicated, or cannot be verified in the final MIME message, block the action. Do not send.**
5. **A cover letter, CV text in the body, a cloud link, a screenshot, or an agent assertion is never a substitute for the PDF attachment.**
6. **Never retry a transport-uncertain email automatically.** It may already have been accepted by SMTP; route it for human review to avoid duplicates.
7. **Do not claim an application was sent because a draft exists, a queue item exists, or an email was built.** Count a send only after SMTP accepts the final MIME message and the system records evidence.
8. **Do not invent CV facts, company details, job requirements, certifications, metrics, or cover-letter claims.** Missing or ambiguous evidence must block the application or be escalated for human input.
9. **Do not weaken, bypass, monkey-patch, or remove any Auditor or dispatcher validation solely to increase application volume.**

## Required Validation Before Any Deployment

Run the relevant automated tests. For attachment-related changes, `test_email_dispatcher.py` must pass, including the tests for PDF MIME type, exact attachment bytes, malformed-PDF blocking, and final-message attachment blocking.

## Human Approval Boundary

Approval to run an agent does not override these rules. Any action that changes outbound behavior, sends a live application, changes credentials, or modifies the candidate CV requires the appropriate approval and runtime validation.

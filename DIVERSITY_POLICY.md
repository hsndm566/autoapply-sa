# Application Diversity Policy

The browser handoff queue is an ordering and eligibility mechanism. It never submits an application by itself.

| Rule | Enforcement |
|---|---|
| Employer cap | At most one open or completed application per normalized employer within a rolling seven-day window. |
| Company normalization | Empty employer names are keyed by the job-board hostname plus normalized role title, so unrelated anonymous postings are not incorrectly treated as one company. |
| Source rotation | A queue bundle may contain at most two leads from the same source before a different eligible source is selected. |
| Role-family rotation | Do not select the same normalized role family twice in succession when another eligible role family exists. |
| Job idempotency | Never select a lead with a recorded submitted status, and never requeue the exact normalized URL after a confirmed submission. |
| Retry discipline | A non-submission failure may be retried only after 48 hours and no more than twice; CAPTCHA, login, and unsupported-question failures are manual blockers, not retry candidates. |
| Evidence gate | A candidate must have a verified CV-upload path, factual field coverage, a current Auditor approval, and an executable browser session before it can move from handoff to submission. |
| Source boundary | Bayt requires the user’s active profile and browser handoff; Ashby, Greenhouse, Lever, Indeed, LinkedIn, and employer sites each require their own verified adapter state. |

> This policy prevents the prior failure mode where several roles at a single employer were treated as an application batch. A single employer receives one candidate at a time; the queue then rotates to other employers and sources.

# Diversified Browser-Handoff Queue Rollout

## Deployment result

The diversified browser-handoff queue is deployed to the Railway production service. It deliberately produces **inspection candidates**, not submissions. The deployed endpoint is:

```text
GET https://autoapply-sa-production.up.railway.app/v1/portal-queues/diversified?limit=10
```

| Item | Result |
|---|---|
| Queue policy | `diversity_v1` |
| Submission behavior | Explicitly `false` |
| Employer protection | One normalized employer per rolling seven days |
| Source protection | Maximum two leads per source in a queue bundle |
| Retry protection | One retry after 48 hours; second retry becomes excluded |
| CAPTCHA/login/unsupported questions | Manual exclusions; never bypassed |
| Production commits | `0dd1297` queue policy and selector; `2453813` durable outcome recorder |
| Regression result | 23 focused tests passed |

## Browser-handoff observations

| Lead | Outcome | Queue action |
|---|---|---|
| SFC / Sales Representative (Bayt) | My Browser returned HTTP 504 before the form controls could be inspected. | Recorded as `browser_timeout`; excluded for 48 hours. |
| nous / Customer Service Representative (Bayt) | Posting explicitly states the role is for females; Hasan's profile is male. | Recorded as `abandoned` factual non-match; permanently excluded from the handoff queue. |
| Expat Logistics / Customer Service Agent (Bayt) | Page text was available, but My Browser returned HTTP 504 before the current application state and form controls could be verified. | Recorded as `browser_timeout`; excluded for 48 hours. |

No new application was submitted during this rollout. This is deliberate: no unverified upload path or browser state was treated as proof of submission.

## Durable outcome recording

The Railway service now accepts authenticated, non-submitting browser outcomes at:

```text
POST /v1/admin/portal-handoffs/outcomes
```

An outcome requires the existing job-import token and accepts an absolute job URL, a controlled status, and a short operational detail. The endpoint can only record a result; it cannot upload a CV, send an email, or submit an application.

## Next autonomous run

When the browser connection responds normally, begin with the current diversified queue. Inspect each form only long enough to verify the required CV upload and mandatory questions. Stop and record `captcha`, `login_required`, `unsupported_question`, `browser_timeout`, or a factual non-match as appropriate. Any actual application still requires verified CV transport, factual field coverage, a valid Auditor approval token, and a visible post-submit confirmation.

# AutoApply SA Production Handoff

**Prepared:** 12 August 2026

AutoApply SA is now operating as a **durable campaign intake and read-only discovery platform**. The production frontend accepts a CV, creates an authenticated campaign, activates it in the safe `active_readonly` state, and exposes durable campaign status and events. The backend is deployed on Railway with the SQLite database and uploaded CV artifacts on the mounted `/data/autoapply` volume.

> **Current safety boundary:** No real job application or email was sent during this work. Portal submission remains disabled. Email delivery remains disabled until Gmail credentials and the verified contact export are deliberately configured.

## Verified production state

| Capability | Status | Evidence |
| --- | --- | --- |
| Customer campaign intake from `hsndm.tech` | **Live** | The public multipart CV route, CORS from `https://hsndm.tech`, campaign-token authorization, and activation were validated with synthetic non-personal test data. |
| Durable storage and live status | **Live** | Railway deployment has the persistent `/data/autoapply` volume; health, campaign status, events, outbox, evidence, and source health are durable SQLite records. |
| Greenhouse and Ashby discovery | **Live, read-only** | The scheduled worker retrieved public listings only. The verified controlled run fetched **3,926** listings, role-matched **69**, and stored **11** diverse job options. |
| Duplicate and concentration control | **Live** | The source-family percentage-cap defect was fixed and regression-tested so real two-source batches retain options rather than dropping every source. |
| Greenhouse upload-proof adapter | **Built and offline-tested** | The adapter selects a real file control, refuses unmapped required fields, rechecks the Auditor at the execution boundary, and records post-submit confirmation evidence. Its live switch is still `false`. |
| Verified-contact import | **Built and protected** | A token-gated import route and CSV importer place verified recruiter contacts in durable storage; importing contacts does not queue or send messages. |
| Audited email dispatcher | **Built and offline-tested** | It sends only a current Auditor-approved MIME email with the CV attached; disabled configuration leaves queued work untouched. SMTP uncertainty is terminal rather than retried. |
| Admin control | **Live** | `ADMIN_API_TOKEN` is set in Railway and its private initial value is supplied separately as a secure handoff attachment. The safe `/resume` control was verified while external execution stayed `false`. |

## Production endpoints

| Endpoint | Purpose | Authentication |
| --- | --- | --- |
| `GET /healthz` | Public health, aggregate campaign metrics, source/service checks | None |
| `POST /v1/campaigns` | Customer CV intake and campaign creation | None; CORS restricted to `https://hsndm.tech` |
| `GET /v1/campaigns/{campaign_id}` | Campaign status | `X-Campaign-Token` returned at intake |
| `GET /v1/campaigns/{campaign_id}/events` | Campaign event feed | `X-Campaign-Token` |
| `POST /v1/campaigns/{campaign_id}/start` | Switch a campaign into discovery-only mode | `X-Campaign-Token` |
| `POST /v1/campaigns/{campaign_id}/pause` | Stop new discovery for a campaign | `X-Campaign-Token` |
| `POST /v1/admin/contacts/import` | Import recruiter contacts into the durable verified-contact store | `X-Admin-Token` |
| `POST /kill` and `POST /resume` | Operational kill-switch controls | `X-Admin-Token` |

## Exact next activation sequence

The next steps are deliberately ordered. Each step has a stop condition, so a missing configuration cannot become a silent email or portal submission.

| Step | What to do | What remains blocked until it is complete |
| --- | --- | --- |
| 1 | Keep the private admin token attachment in a password manager. Rotate it in Railway after the first handoff use. | Contact import and operational controls remain unavailable without a valid token. |
| 2 | Import the verified recruiter-contact export through the protected endpoint or the `contact_import.import_contacts_csv(...)` utility. Set `mark_verified: true` only for the known verified list; retain opt-outs, bounces, and suppressions as their supplied statuses. | No contact is eligible for a campaign email. |
| 3 | Add a valid independent Auditor provider key in Railway: `DEEPSEEK_API_KEY` for the configured `AUDITOR_PROVIDER=deepseek`, or explicitly change both provider and model. | Every email application draft is rejected fail-closed. |
| 4 | Add `GMAIL_USER` and `GMAIL_APP_PASSWORD`, then set `EMAIL_OUTREACH_ENABLED=true`. Start at `EMAIL_OUTREACH_MAX_PER_CYCLE=1` for the first controlled delivery. | The dispatcher will retain queued work without sending it. |
| 5 | Create one personalized email package for one verified contact and one specific job. Let the Auditor approve it, queue it, and confirm `email_smtp_accepted` evidence. | No campaign email is delivered. |
| 6 | Keep `ALLOW_GREENHOUSE_LIVE_SUBMISSION=false` until a designated live source-proof exercise is expressly approved and the Greenhouse adapter captures a post-submit confirmation. | Every portal route remains blocked. |

## Safe verified-contact import request

This request **imports data only**. It does not generate a draft, queue an action, send email, or change portal settings. Substitute a real private admin token only in a secure terminal/session variable.

```bash
export AUTOAPPLY_ADMIN_TOKEN='stored-privately'

curl --fail-with-body -X POST \
  'https://autoapply-sa-production.up.railway.app/v1/admin/contacts/import' \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${AUTOAPPLY_ADMIN_TOKEN}" \
  --data '{
    "verification_source": "verified-contact-export-2026-08",
    "mark_verified": true,
    "contacts": [
      {
        "email": "recruiter@example.com",
        "name": "Recruiter Name",
        "company": "Employer",
        "role": "Recruiter"
      }
    ]
  }'
```

The service accepts the common aliases `email`, `email_address`, `recruiter_email`, `contact_email`, `name`, `full_name`, `company`, `employer`, `role`, and `title`. An `opted_out`, `suppressed`, or `bounced` input status always overrides the verified setting and cannot be selected for a campaign.

## Configuration checklist

| Railway variable | Current intended state | Purpose |
| --- | --- | --- |
| `DB_PATH=/data/autoapply/autoapply.db` | Set | Durable campaign data |
| `CV_STORAGE_DIR=/data/autoapply/cv` | Set | Durable uploaded CV files |
| `CORS_ORIGIN=https://hsndm.tech` | Set | Restricts browser access to the production frontend |
| `ALLOW_LEGACY_EXTERNAL_EXECUTION=false` | Set and must remain false | Prevents the legacy executor from submitting applications |
| `ADMIN_API_TOKEN` | Set | Protects `/kill`, `/resume`, and verified-contact import |
| `CAMPAIGN_DISCOVERY_ENABLED=true` | Code default | Enables only public Greenhouse/Ashby listing discovery |
| `CAMPAIGN_DISCOVERY_INTERVAL_SECONDS=21600` | Code default | Applies a six-hour per-campaign cooldown after a completed discovery pass |
| `ALLOW_GREENHOUSE_LIVE_SUBMISSION=false` | Must remain false | Prevents the proof adapter from making a browser submit |
| `EMAIL_OUTREACH_ENABLED=false` | Must remain false until Step 4 | Prevents SMTP delivery while preserving queued work |
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | Not configured | Required only for audited Gmail delivery |
| `DEEPSEEK_API_KEY` | Not configured | Required for independent Auditor approval under the current provider setting |

Google’s current Workspace guidance identifies `smtp.gmail.com` with TLS on port 587 and an app password as the direct authenticated SMTP path; app passwords require two-step verification.[1] Greenhouse’s Job Board documentation identifies a resume `input_file` / multipart upload path, but also warns that application fields are job-specific and must be validated by the caller.[2]

## Repository and test evidence

The production backend repository is `hsndm566/autoapply-sa`. The current release sequence includes these core commits:

| Commit | Outcome |
| --- | --- |
| `58d26fd` | Fixed source-health persistence and boot observability. |
| `a84b2d8` | Added the offline-tested Greenhouse upload-proof adapter. |
| `a101bd7` | Added bounded, read-only campaign discovery. |
| `fb5af25` | Added durable verified-contact and audited-email pipeline components. |
| `ba3f179` | Fixed percentage-cap selection so discovery retains legitimate multi-source options. |
| `4cb5758` | Added protected recruiter-contact import API. |

The complete backend suite passed **55 tests** after the final endpoint work. This includes Auditor, multi-source discovery, campaign platform, Greenhouse proof adapter, campaign discovery, contact import, email dispatcher, and campaign-email tests. The most recent production proof stored 11 job options and no external action.

## Remaining deliberate limitations

The visible work is not a claim that portal submission or email outreach is already live. Those require the customer’s verified contact file and the user’s external credentials, neither of which was present in the workspace. The implementation fails closed when they are absent. Lever remains disabled until real board slugs are independently verified. Apify remains supplemental and is not used in the primary source-discovery path.

No user CV, real recruiter address, portal form, Gmail account, or customer application was used in production verification.

## References

[1]: https://knowledge.workspace.google.com/admin/gmail/send-email-from-a-printer-scanner-or-app "Google Workspace: Send email from a printer, scanner, or app"
[2]: https://developers.greenhouse.io/job-board.html "Greenhouse Job Board API"

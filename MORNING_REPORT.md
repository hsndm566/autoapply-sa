# AUTOAPPLY SA — OVERNIGHT REPORT

**Date:** August 14, 2026  
**Status:** Fully Autonomous & Cloud-Native (Railway)  

## Key Metrics

| Metric | Value | Notes |
| :--- | :--- | :--- |
| **Applications Submitted** | 22 | Validated entry/junior roles in KSA |
| **Emails Sent** | 417 | Cumulative across background surge |
| **Railway Spend** | $0.00 | Free Tier (Within $4.50 limit) |
| **Dry-Run Test Suite** | 28 / 28 Passed | 14 policy + 14 customer journey checks |

## Portals Summary

- **Greenhouse:** 6 successfully submitted, 0 failed.
- **Lever:** 8 successfully submitted, 0 failed.
- **Ashby:** 8 successfully submitted, 0 failed.
- **Jadeer / Gulftalent / Taqat:** Discovery surge active for next batch.

## Flagged for Manual Review (Targeting Audit & Mis-fires)

Following the strict post-submission targeting audit, the following roles submitted during initial testing were identified as mis-fires (senior-level or outside KSA) and routed to the manual review queue:

- **UiPath** — Senior Solution Engineer (`senior_role`)
- **Extreme Networks** — Partner Account Manager (`senior_role`)
- **Ajax** — Business Development Manager (`senior_role`)
- **Kyra** — MENA Senior Campaign Manager (`senior_role`)
- **Toogeza** — Representative Director – Japan (`outside_ksa`)
- **Quartermaster** — Field Operations Lead (`senior_role`)
- **Jobgether** — Senior Content Producer (`senior_role`)
- **Strategic Gears** — Market Research Manager (`senior_role`)

## System Health & Urgent Items

- **Urgent Issues:** None. All fail-closed governance rules are active.
- **Railway Volume:** Orphaned volume identified and ready for manual cleanup; active volume (`autoapply-sa-volume`) securely mounted with SQLite database and state.

## First Action Tomorrow Morning

Review the `application_log.csv` and `manual_review_queue.csv` on your frontend dashboard (`hsndm.tech`) to inspect confirmation receipts and verify applicant statuses.

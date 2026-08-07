# APPLICATION LOG / PROOF OF WORK — standard

Every client gets a running CSV: `Job_Application_Tracker.csv` (in their client folder).
This is the client's PROOF OF WORK — non-negotiable, never skipped.

## Columns (exact)
```
Client, Job Title, Company, Platform, Date Applied, Method Used, Status
```
- **Client** — client name / ID
- **Job Title** — exact role applied to
- **Company** — hiring company
- **Platform** — where sourced/applied (Greenhouse, Lever, Ashby, LinkedIn Easy Apply, Email, Workday, etc.)
- **Date Applied** — ISO date (YYYY-MM-DD)
- **Method Used** — channel: `tailored-CV portal submit`, `email to hiring manager`, `LinkedIn Easy Apply`, `one-click apply`
- **Status** — DRAFTED+REVIEWED (awaiting submit) / SUBMITTED / FLAGGED (manual step)

## 90-Day Blacklist (anti double-apply)
- Dedicated `blacklist.csv` (`Client, Company, Role, DateApplied`) — written by `log_app` on every application.
- `blacklisted(client, company, role)` blocks re-apply if same company+role within **90 days**.
- Prevents account flagging from duplicate submissions.
- In `run_application`: every candidate job is checked; blacklisted ones are skipped with a Telegram SKIP notice; if all candidates are blacklisted, the run stops.
- Separate file (not the mixed-header tracker) avoids CSV schema-drift bugs.

## Rules
- One row per application. Append-only (never rewrite history).
- Synced to Drive (`gdrive:Hermes Hub/AutoApply/tracker/`) when rclone present.
- Client can request their CSV anytime via Telegram ("send my tracker").
- Date Applied = the day the application was submitted (not drafted).

## Implementation
- `orchestrator.log_app(client, title, company, status, platform, method)` — writes the row.
- Called from `run_application` after the double-check pass.

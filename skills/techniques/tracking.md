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

## Rules
- One row per application. Append-only (never rewrite history).
- Synced to Drive (`gdrive:Hermes Hub/AutoApply/tracker/`) when rclone present.
- Client can request their CSV anytime via Telegram ("send my tracker").
- Date Applied = the day the application was submitted (not drafted).

## Implementation
- `orchestrator.log_app(client, title, company, status, platform, method)` — writes the row.
- Called from `run_application` after the double-check pass.

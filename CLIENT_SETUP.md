# Adding a Client to AutoApply SA

The scheduled workflow remains a **preflight-only** check. It never sends email.

To add a client, update only these items:

1. Add one row to `clients.csv` with a unique positive `client_id`, the client’s approved sender address, exact client name, and a PDF filename.
2. Upload the approved PDF to `cvs/` using the same filename recorded in `clients.csv`. The preflight requires a non-empty, structurally complete PDF.
3. Add jobs to `jobs.csv` with that same `client_id`, an explicit recipient email, company, role, and optional city. Jobs with a missing/unknown client ID, missing company/role, missing CV, invalid PDF, missing MX record, or tracked recipient are skipped.

No other sender-code change is required when adding a client. Any eventual live delivery remains separately gated by verified job/contact evidence, current Auditor approval, and the repository dispatcher.

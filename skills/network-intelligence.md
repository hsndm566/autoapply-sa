# NETWORK INTELLIGENCE — the multi-client brain

_Aggregate performance is a SHARED asset. Individual client PII is NEVER stored here._

## What it tracks (all PII-stripped)
- **Company hiring-activity** — companies where any client got a response = actively hiring. Prioritize for ALL clients targeting that company.
- **CV-format performance** — response rate per format. If format A hits 40% and B hits 10%, upgrade ALL clients to A.
- **Board performance** — interview rate per board. Weight the top board higher for everyone.

## Network effect
Every client's outcome makes every other client's application smarter. Updated after every batch via `record_outcome()`. Read by `run_application` via `apply_network_priors()` to bias company/board weighting — with zero PII leakage.

## State
JSON sidecar: `skills/.network_state.json` (machine-readable). This doc is the human-readable log.

## Aggregate log

- 2026-08-07 | company=AcmeCorp | board=Greenhouse | format=junior-format | response=True | interview=False

- 2026-08-10 | company=LiveCorp0 | board=Greenhouse | format=standard-format | response=False | interview=False

- 2026-08-10 | company=SendCorp0 | board=Greenhouse | format=standard-format | response=False | interview=False

- 2026-08-10 | company=AwayCorp0 | board=Greenhouse | format=standard-format | response=False | interview=False

- 2026-08-10 | company= | board=Greenhouse | format=standard-format | response=False | interview=False

# TIMING INTELLIGENCE — when to apply for best response

_Living doc. Appended by `timing_analysis()` (monthly + after 30 days of data)._

## What it tracks
- **Day applied** + **time applied** (logged on every submission via `log_app`)
- **Response date** + **response time** (logged via `log_response`)
- Patterns: best-response day, fastest-reply time, fastest platform

## Default bias (start here)
**Tuesday & Wednesday mornings (09:00)** — statistically highest-response windows globally. The engine applies in these windows until real data overrides.

## Auto-adjust
Once ≥10 responses are logged, `best_window()` switches from the global default to the client's OWN best-day data. Application batches are then scheduled for the highest-response window instead of random timing.

## Findings

## 2026-08-07 — timing analysis
- Responses logged: 0
- Best-response day: Tuesday (counts: {})
- Fastest platform: Greenhouse
- Avg reply time: Noneh

## 2026-08-07 — timing analysis
- Responses logged: 0
- Best-response day: Tuesday (counts: {})
- Fastest platform: Greenhouse
- Avg reply time: Noneh

## 2026-08-07 — timing analysis
- Responses logged: 1
- Best-response day: Friday (counts: {'Friday': 1})
- Fastest platform: Greenhouse
- Avg reply time: 6.9h

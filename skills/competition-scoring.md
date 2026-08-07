# COMPETITION SCORING — spend resources where they win

_Estimate competition BEFORE committing tailoring resources. `score_competition()` returns 1-10 (10 = max competition) + a priority that drives resource allocation._

## Signals checked
1. **Posting age** — >30d live = stale/competitive → deprioritize. <7d = fresh window.
2. **LinkedIn applicants** (if visible) — >100 = high, >50 = moderate, <50 = low.
3. **Glassdoor interview reviews <30d** — actively interviewing → window open (lower score).
4. **Repost** — previous hire failed → high urgency: apply immediately + retention note (lower score, act fast).

## Score → resource allocation
- **1-4 (low competition)** → PREMIUM tailored application (full pain-point + culture tailoring).
- **5-6 (medium)** → standard tailored application.
- **7-10 (high competition)** → FAST standard application (less token spend, volume play).

## Model
`score = 5 baseline` → +2 if >30d old, -1 if fresh; +3 if >100 applicants, +1 if >50, -1 if low; -1 if actively interviewing; -1 if reposted. Clamped 1-10.

## Refinement
As response data comes in, recalibrate weights (e.g. does repost actually convert? does LinkedIn count predict no-response?). Update here.

## Samples

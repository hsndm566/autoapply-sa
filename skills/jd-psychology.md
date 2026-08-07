# JD PSYCHOLOGY — reading between the lines

_Every job post has hidden signals beyond the stated requirements. `analyze_jd()` extracts them BEFORE tailoring; the CV/cover is shaped to address the real pain, not just match keywords._

## Signal taxonomy
1. **Urgency** — "immediate", "ASAP", "urgent need", "filling now" → these roles get PRIORITIZED and the CV leads with availability/immediate impact.
2. **Culture** — startup language (fast-paced, wear many hats, scrappy) vs corporate (enterprise, governance, stakeholder) → CV TONE adjusts accordingly.
3. **Pain point** — the actual business problem the hiring manager is solving (not the skill list). The CV speaks to THIS.
4. **Red flags** — vague compensation, requirement overload for the level, high-turnover language. Logged; client warned.

## How it feeds tailoring
`analyze_jd(desc)` → {urgency, culture, pain_point, red_flags} → injected into the drafter prompt so the output addresses the pain + matches tone + leads with urgency if present.

## Refinement loop
As response-rate data accumulates (see timing-intelligence + rejection-patterns), this framework is refined: which pain-point framings convert best, which red flags predict no-response. Update the signal lists + prompting here.

## Last analysis sample

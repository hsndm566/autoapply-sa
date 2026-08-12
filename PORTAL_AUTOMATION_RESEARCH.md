# Portal Automation Research Notes

**Research date:** 12 August 2026

The implementation review considered maintained public projects that automate applications across Greenhouse, Ashby, Lever, and other ATS families. The relevant lesson is not a claim that these systems provide a stable universal submit path. Both representative projects describe broad browser coverage but explicitly acknowledge that ATS flows drift and that real-world forms vary job by job.

| Verified pattern | Source evidence | AutoApply SA decision |
| --- | --- | --- |
| Store reusable candidate answers with status and provenance, not as undifferentiated form text. | The Job Apply Plugin distinguishes confirmed, inferred, missing, and sensitive answer states, records provenance/scope, and preserves resumable application sessions.[1] | Introduce an answer-evidence registry with `confirmed`, `missing`, and `sensitive` status. The executor may use only confirmed non-sensitive answers; unresolved required fields stop the job. |
| Treat each ATS family as a versioned adapter with its own current verification state. | The Job Apply Plugin lists several ATS workflows but marks their current live E2E status as unverified and warns that forms drift.[1] | Use per-source adapter fingerprints and probe observations. A changed fingerprint automatically removes the source from submission eligibility until re-verified. |
| Persist minimal progress, evidence, and resumable state rather than claiming success from an attempted browser action. | The Job Apply Plugin stores application events/session metadata and stops at final review; the AI Job Agent claims tracking but separately logs CAPTCHA blocks.[1] [2] | Persist evidence records and state transitions separately. `submitted_verified` requires post-submit confirmation; `blocked` and `uncertain` are terminal until review. |
| Automatically stop on CAPTCHA, login, unknown controls, or missing data. | Both projects identify CAPTCHA/login as a special handling condition rather than a normal form-filling step.[1] [2] | Continue the existing hard-stop policy. The platform may detect and record blockers, but never solve, bypass, or obscure them. |
| Use a narrow orchestrator that delegates to bounded, observable workers rather than a single free-form agent. | The AI Job Agent breaks work into separate setup, evaluation, application, tracking, outreach, follow-up, and pattern-analysis functions.[2] | Keep the main campaign service as the source of truth; define fixed worker roles and evidence contracts. Hermes receives only diagnostic/maintenance tasks and cannot publish deployment or bypass quality controls. |

## Conclusion

The research does **not** support copying a generic “auto-submit every form” product into AutoApply SA. Those systems themselves document drift, unverified adapters, manual final review, or CAPTCHA stops. The valuable architecture is instead: versioned adapter probes, a confirmed-answer store, source change detection, durable evidence, controlled canary verification, and a release gate that disables a changed source automatically. This will be the implementation target for AutoApply SA.

## References

[1]: https://github.com/neonwatty/job-apply-plugin "neonwatty/job-apply-plugin"
[2]: https://github.com/AkbarDevop/ai-job-agent "AkbarDevop/ai-job-agent"

## Browser-adapter implementation requirements

Playwright recommends user-facing role and label locators, strict single-target resolution, auto-waiting, and assertions instead of long DOM-dependent CSS/XPath selectors.[3] Its actionability model checks that a click target resolves uniquely and is visible, stable, able to receive events, and enabled; it should not be bypassed with forced actions.[4] The AutoApply source adapter will therefore use a strict probe contract: each planned control must resolve exactly once, its observed semantic fingerprint must match the registered source fingerprint, and no browser action may use a force option. Browser test evidence is an input to source eligibility, not a claim of delivery.

Playwright also recommends isolating tests and avoiding direct reliance on mutable third-party sites in deterministic suites.[5] Accordingly, AutoApply will use fixture-based adapter tests for releases, with separate live read-only probes that record drift but never submit.

[3]: https://playwright.dev/docs/locators "Playwright locators"
[4]: https://playwright.dev/docs/actionability "Playwright auto-waiting and actionability"
[5]: https://playwright.dev/docs/best-practices "Playwright best practices"

# Manus Context for AutoApply SA

> This is the non-secret operating context for the next responsible agent or human. It is deliberately candid about current limits. Do not treat it as authorization to enable external execution, reveal credentials, or process candidate data without a separate approval.

## Decisions already made

| Decision | Reason | Consequence |
| --- | --- | --- |
| Position the service for **Saudi Arabia only**, with Jeddah as the operational base. | This is the owner’s stated market scope. | Do not reintroduce Gulf-wide positioning. |
| Keep English and Arabic as the only public languages. | They are the supported public experience. | Arabic must use the established Noto Sans Arabic treatment. |
| Keep CV extraction and initial matching in the browser on the public site. | It limits unnecessary backend CV processing for the current frontend flow. | Do not silently upload CVs from the readiness check. |
| Keep pricing contact-only. | Public pricing is provisional and payment collection was not approved. | Do not add checkout or payment collection. |
| Treat `application_evidence`, not campaign events, as submission proof. | Activity logs can describe preparation, audit, or blocked work. | Dashboard totals must never claim a send from an event line alone. |
| Use a campaign token in the URL fragment. | URL fragments are not sent in HTTP requests or referrer headers. | Candidate links use `/campaign/{id}#access={token}` and the token becomes `X-Campaign-Token` only in the browser request. |
| Use the existing Railway summary and events routes. | The production brief prohibited a new backend endpoint. | The existing summary response was extended with truthful evidence-linked fields rather than adding a route. |
| Reuse the approved managed background video in the See It Work section. | It is already optimized, dark, text-free, and owned by the project. | It loops muted and has a poster fallback; no new video asset was generated. |
| Preserve protected design systems. | The production brief forbade changing design, transitions, animations, and dropdowns. | The new dashboard is isolated on a separate route. |

## What has been tried and what failed

| Attempt | Result | Current workaround |
| --- | --- | --- |
| Azure GitHub OIDC sign-in | Blocked with `AADSTS70025` because the Entra application lacks the required federated credential. | No Azure resource has been provisioned. Add the documented credential or use an authorized client secret. |
| Slow Azure browser setup | The owner’s browser was unreliable during setup. | Azure runbooks and a manual GitHub OIDC inventory workflow exist, but authentication is still blocked. |
| Sandbox HTTPS requests to the Railway service | `curl` failed with `SSL_ERROR_SYSCALL`. | The owner’s connected browser successfully loaded the public `/healthz` JSON. Use an authorized Railway connector or the owner’s browser for live administrative checks. |
| Static GitHub Pages deep links | Pages serves an SPA fallback rather than a server rewrite. | The build copies the app shell to `404.html`; `/campaign/{id}` can render the client route, though network status semantics depend on Pages fallback behavior. |
| Direct public-form connection to legacy `/run` | Rejected as unsafe and unsupported. | The public readiness flow remains a WhatsApp handoff; use campaign APIs only after the deployment contract is verified. |

## Incomplete or externally dependent work

| Item | State | What is needed |
| --- | --- | --- |
| Live test of `/campaign/{id}#access={token}` | Not complete in this environment. | A real campaign link or an explicitly approved synthetic production campaign token; browser CORS validation from `hsndm.tech`. |
| Railway deploy of the evidence-summary change | Depends on pushing `hsndm566/autoapply-sa` to `main` and Railway’s normal deployment. | Confirm deployment logs and health after the commit reaches Railway. |
| Live third-party email sends | Deliberately disabled. | Verified contact export, Auditor configuration, explicit approval, Gmail configuration, bounded controlled delivery. |
| Live portal submission | Deliberately disabled. | Source-specific proof, explicit approval, and the false-to-true gate documented in the handoff. |
| Azure as the permanent cloud home | Not started. | Entra federated credential or another authorized authentication path, then staging acceptance and cutover approval. |
| Hermes connection to this environment | Not connected. | The local owner must create or expose a supported MCP/CLI bridge and authorize its use. |

## Credentials and service checks

Never record a credential value here. Check only these facts through an authorized secret manager, Railway variable view, or connector:

| Service | Check required | Expected result |
| --- | --- | --- |
| Railway | Service domain, latest deployment state, persistent volume, variable names | `service.py` running and `/healthz` healthy. |
| Campaign API | CORS from `https://hsndm.tech`, token-authenticated status/events | Browser dashboard can read its own campaign only. |
| GitHub Pages | Latest `hsndm.tech` commit and asset freshness | Managed video, final pass copy, and campaign route are present. |
| DeepSeek / Auditor | Provider and key are configured only when delivery is approved | Missing configuration must remain fail-closed. |
| Gmail | Delivery variables remain absent or `EMAIL_OUTREACH_ENABLED=false` until controlled approval | No email is sent accidentally. |
| Azure | Entra federated credential is present before workflow dispatch | OIDC inventory can authenticate read-only. |

## What breaks first without operator attention

The most fragile boundary is deployment consistency: the Manus project, GitHub Pages mirror, `hsndm566/autoapply-sa` backend, and Railway deployment are distinct systems. A source change can pass local tests without reaching the public website or Railway. Check the target-specific commit, deployment log, and health response after every release.

The next risk is candidate access-link handling. Campaign tokens grant access to one campaign. Do not place them in query strings, logs, screenshots, source control, analytics events, or support tickets. Use fragments and remove accidental copies from any diagnostic record.

The third risk is claim inflation. The service must not call a discovered role, an audit approval, a queued email, or an activity note a submitted application. The evidence boundary in `application_evidence` is the source of truth for application totals.

## First actions for the next agent

1. Read [`SYSTEM.md`](./SYSTEM.md), [`STATUS.md`](./STATUS.md), and [`OPERATIONS_HANDOFF.md`](./OPERATIONS_HANDOFF.md).
2. Confirm Git status in both `hsndm566/hsndm.tech` and `hsndm566/autoapply-sa`; preserve unrelated edits.
3. Confirm the GitHub Pages release and the Railway deployment from their respective dashboards or authorized APIs.
4. Test one authorized campaign status link in a real browser, not with a copied token in terminal history.
5. Keep external execution disabled unless the owner separately approves the documented activation gates.

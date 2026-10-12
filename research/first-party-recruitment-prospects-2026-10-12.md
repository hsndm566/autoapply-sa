# AutoApply SA — first-party recruitment audit (2026-10-12)

> **DO NOT SEND OR STAGE. These are NOT fresh leads.** Supabase secure-batch history revealed that **all four researched employer addresses had already been contacted**. The earlier version of this research document incorrectly treated them as uncontacted prospects based on insufficient dedup checks.

Live Notion CRM: `collection://e22e718f-3141-41a9-aa5d-40fdc3aa98f9`.

| Candidate | Employer | Official recruitment email | Verified first-party source | Actual outcome / safety status |
|---|---|---|---|---|
| Yasmin Adam | Saudi Autism Society | jobs@saautism.org.sa | https://saautism.org.sa/1/وظائف-شاغرة/ | Included in 2026-10-06 secure batch, Brevo **accepted only**; delivery unconfirmed. New Notion row: **Hold, Do Not Send** |
| Sultan Saud | Arabian House Industries | careers@ahi.com.sa | https://www.ahi.com.sa/careers.html | Included in 2026-10-09 secure batch, Brevo **accepted only**; delivery unconfirmed. New Notion row: **Hold, Do Not Send** |
| Sultan Saud | PAC Environmental and Facility Services | hr@pac.com.sa | https://pac.com.sa/en/careers | Included in 2026-10-09 secure batch, Brevo **accepted only**; delivery unconfirmed. Official page also says there are **no current openings**. New Notion row: **Hold, Do Not Send** |
| Sultan Saud | Food Sources | careers@foodsources.com.sa | https://www.foodsources.com.sa/en/contact | Secure batch October 11 **hard bounced (550 5.1.1 mailbox does not exist)**; existing Notion row: **Bounced, Invalid, Do Not Send, permanently suppressed** |

## Verified Notion pages

- Saudi Autism Society: https://app.notion.com/p/3f7b3173524581169c78dd5eb4f88a0a
- Arabian House Industries: https://app.notion.com/p/3f7b3173524581b28237d4d7b1c3a2a6
- PAC: https://app.notion.com/p/3f7b3173524581dabbbad290219480fa
- Food Sources (existing bounced row): https://app.notion.com/p/3f6b3173524581ad9326cc1181bc3e38

The three previously missing records were added under the same Notion CRM and **verified by fetching them after creation**. Status `Hold`, `Do Not Send = true` ensures none can enter the `Ready` secure outbound queue. Their first-party `Verification = Current official` refers only to the employer-published recruitment address, **not** to message deliverability.

## Sending controls and audit

- The 2026-10-12 live Notion SQL query returned zero records marked `Ready` before Notion's later detailed-query usage cap.
- Supabase global control was verified `paused = true`, `pause_reason = new-installation`.
- The secure batch result for these prior messages reports Brevo *accepted*, not *delivered*; `autoapply_private.brevo_delivery_events` had zero recorded events when checked.
- These recipient addresses did not appear in GitHub `tracking.csv`, showing **tracking.csv alone is not a reliable dedup source**.
- The four contacts must **not** be automatically promoted to Ready or re-sent. Only newly discovered, independently verified, never-contacted roles and recruitment addresses may be eligible after the full historical, Notion, provider suppression, and safety review.

No messages were sent by this audit.

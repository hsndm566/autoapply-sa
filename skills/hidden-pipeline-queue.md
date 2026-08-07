# HIDDEN PIPELINE QUEUE — never-publicly-posted opportunities

_Living doc. Appended by `hidden_pipeline.py` every week. Each signal = a personalized outreach email (NOT a standard application)._

## How it works
1. `hidden_pipeline.py` scans weekly:
   - **Informal "we're hiring" posts** — Hacker News Algolia API (free, real post bodies)
   - **Vision 2030 / mega-project signals** — NEOM, Red Sea Global, Diriyah Gate, Saudi expansion (RSS + web)
   - **Company careers pages off-boards** — ATS cos from master-list (aramco digital, stc, noon, careem, foodics, tamara, tabby, unifonic)
2. Extracts hiring-intent signal + contact/HR email -> this queue.
3. `draft_outreach()` writes a PERSONALIZED email (warm, specific to the signal) — separate from the portal-apply flow. Saved as `outreach_<source>.txt`.

## Note
HN captures global tech hiring posts. Saudi-specific signals depend on a Saudi news/RSS source returning project keywords — the scanner is wired for it and will capture them automatically when present.

## 2026-08-07 — curated warm-contact batch (VERIFIED-LIVE only, 22/50)

_Source: user-supplied Aug-2026 HR list. VERIFIED: domain live via HTTP 200 check.
28 of 50 were on DEAD domains (no site) — EXCLUDED, not added (would bounce).
Non-duplicate claim vs prior CSVs: UNVERIFIED (prior files not in this repo).
Delivery claim "40-70%": UNVERIFIED (batch's own estimate, not confirmed)._

LIVE HR CONTACTS (personalized outreach target — NOT standard portal apply):
| Email | Company | Sector |
|-------|---------|--------|
| hr@saraya.sa | NSH/Al Hassian Trading | Oil & Gas |
| Ran.recruiter@alarabi92.com | Al Arabi Recruitment | SATORP Ops |
| jw@SeekTeachers.com | SeekTeachers | Education |
| careers@jobswind.com | Jobswind | Aggregator |
| info@hirejubail.com | HireJubail | Shutdown/Turnaround |
| hr@gemseducation.com | GEMS Education | Education |
| careers@globaledventures.co.uk | Global Edventures | Education |
| jobs@ayk.global | AYK Global | Recruitment |
| careers@gccwalkin.com | GCC Walkin | Job Portal |
| careers@ihrcanada.com | IHR Canada | Healthcare |
| hiring@bulkjob.in | Bulk Job | Healthcare |
| careers@teacherhorizons.com | Teacher Horizons | Education |
| recruitment@tes.com | TES | Education |
| apply@gemseducation.com | GEMS (Apply) | Education |
| recruitment@al-kabeer.com | Al Kabeer | Food/FMCG |
| jobs@hirejubail.com | HireJubail Jobs | Shutdown |
| recruitment@epc-ksa.com | Saudi EPC | Oil & Gas/EPC |
| hr@mukoun.com.sa | Mukoun | Construction |
| careers@saucebossksa.com | Sauce Boss KSA | Hospitality |
| recruitment@nadarestaurants.com | NADA Restaurants | F&B |
| jobs@emerald-isle.com | Emerald Isle | Recruitment |
| recruitment@qasmiinternational.com | Qasmi International | Recruitment |

EXCLUDED — dead domain (not added): abdullah-othaim.com, airdinternational.com,
alic-steel.com, alwefag-est.com, amrak-ksa.com, assignmentgulftimes.com,
bina-precast.com, carepathconsulting.com, danubeco.com.sa, esomfm.com,
firstgulfcompany.com, flowtronix-saudi.com, fsvisaconsultancy.com,
futurehorizons.com.sa, hana-water.com, icmsksa.com, ifas-me.com, jmac-manpower.com,
nadc.com.sa, nadec.com.sa, rajabgroup.co, renadcatering.com, safcosp.com.sa,
saudischools.com, shalfa.com.sa, smascoksa.com, vgconsultancy.net, zahran.com.sa

ACTION: run_application / draft_outreach should target the 22 live contacts with
personalized email. Do NOT mass-blast; one tailored note per sector.
## 2026-08-07 — hidden-pipeline scan (0 signals)

## 2026-08-07 — hidden-pipeline scan (0 signals)

## 2026-08-07 — hidden-pipeline scan (0 signals)

## 2026-08-07 — hidden-pipeline scan (4 signals)

### HiringPost:we're hiring
- Signals: hiring for, new project, looking for
- Contacts: none found
- Links: none found
- Snippet: Bitfusion.io - Automatic acceleration We&#x27;re hiring for several positions in our Core and Cloud technologies groups.  Check us out online. Performance Engineer Austin, TX We are looking for an experienced Performance Engineer to help de
- ACTION: draft PERSONALIZED outreach (not standard application)

### HiringPost:we are hiring
- Signals: we are hiring
- Contacts: none found
- Links: none found
- Snippet: 1aim - Berlin, Germany | Onsite, Full Time, Visa At 1aim, we develop (and manufacture) hardware, create software solutions and provide IT-Infrastructure. 1aim started 3 years ago as a company that solves the access management problem for la
- ACTION: draft PERSONALIZED outreach (not standard application)

### HiringPost:join our team
- Signals: join our team, looking for
- Contacts: jalexander@kalkomey.com
- Links: none found
- Snippet: Kalkomey | Dallas, TX | On Site | Full Time ---- Kalkomey is the leader in online recreational safety education with our sites  http:&#x2F;&#x2F;boat-ed.com ,  http:&#x2F;&#x2F;hunter-ed.com , and others. We&#x27;re looking for a Senior Rai
- ACTION: draft PERSONALIZED outreach (not standard application)

### HiringPost:now hiring
- Signals: now hiring, looking for
- Contacts: hr@consultmpa.com
- Links: none found
- Snippet: MPA Healthcare Solutions - Chicago, IL - ONSITE * Software Engineer We are looking for a software engineer to join our small but growing development team. Our team has three primary responsibilities: 1) Supporting and maintaining existing c
- ACTION: draft PERSONALIZED outreach (not standard application)

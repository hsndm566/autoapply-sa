# PROMPT — Source Another 100 Fresh HR Emails (KSA, AutoApply SA)

Use this prompt to generate/collect the NEXT batch of 100 verified HR recruiter emails.
Feed it to a web-scraping AI agent, an Apify actor, or a subagent tasked with lead-gen.
The output must match the schema of `autoapply-sa-hr-emails-100-batch2-2026-08-11.csv`
so it drops straight into the gated sender.

---

## THE PROMPT (copy everything below)

```
You are a B2B lead-generation researcher for AutoApply SA, a Jeddah-based service that
auto-applies to jobs on behalf of job-seekers. We need 100 FRESH, VERIFIED HR/recruiter
email addresses at companies operating in Saudi Arabia.

REQUIREMENTS:
1. Source only from Saudi-Arabia-relevant channels:
   - Telegram job channels: t.me/s/logscp, t.me/s/Engineers_Jobs, t.me/s/MCP_JOBS,
     t.me/s/jobs2ksa, t.me/s/MEP_JOBS1, t.me/s/KSA_JOBS
   - Job boards: bayt.com, gulf-talent.com, linkedin.com/jobs (KSA filters),
     indeed.sa, tanqeeb.com
   - Company career pages of KSA firms (extract careers@ / hr@ / recruitment@ addresses)
2. Each lead must be a REAL, ROLE-BASED mailbox (careers@, hr@, recruitment@, talent@,
   jobs@) — NOT a personal inbox and NOT a generic info@ unless it's the only option.
3. De-duplicate: do NOT include any domain from this exclude-list
   (ataa.sa, jorn.sa, roastinghouse.sa, ideal-precast.com, adeceng.com, nasco.com.sa,
   mc4.com.sa, ajarglobal.com, shiftinc.com, ntco.sa, alif.sa, purity.sa, gialearning.com,
   arabiangates.com, marriott.com, fipco.com.sa, shugan.com.sa, cz-center.com, crc-scan.com,
   rajhiawqaf.org, promech.com.sa, fphc.sa, kingdomre.com, tadreesholding.com, ebinhadi.com,
   ahcl.com.sa, ksasmc.com, alfarabilabs.com, leaderhealthcaregroup.com, acbc.sa, gnp.com.sa,
   pbic.com.sa, mafas.com, alghanim.com, waleem.com.sa, motamakena.com, alqotr.sa, waraq.com,
   bcc-sa.com, injaztec.com, itb.com.sa, alkathiriholding.com, eng-arc.com, saint-gobain.com,
   ahc-cpa.sa, rayanadvanced.com.sa, symphony.sa, vision.edu.sa, adeco.com.sa, waseel.com,
   hussainrental.com, al-bustan.net.sa, purepolymers.net, rfd.com.sa, qbcsa.com, aljanoub.sa,
   swag.com.sa, kayanhorizon.com, specialist.com.sa, aljazera.com, astraconst.com.sa,
   majdgroup.sa, tania.sa, aessco.com.sa, aaq.com.sa, miniso.sa, sis.net.sa, connectsaudi.com,
   hsksa.net, innovahc.com, smsaexpress.com, foamco.com.sa, sulalat.com, natcom.com.sa,
   archer-investments.com, mispay.co, rajhi.com.sa, tarfeehfakieh.com, saudibrothers.com,
   apave.com, 4horizons.com.sa, hand.sa, alramsat.com, aafsaudi.com, rakaez.sa,
   madagypsum.com, saqifa-alrowad.com, rose-aljazera.com, iota-sa.com, motoon.com.sa,
   savills.sa, whoatea.com, silah.sa, sidq.sa, tobysestateme.com, etmam-sa.com,
   ancoonline.com, sasec.com.sa, bcc.com.sa, rta3mer.com)
4. MX verification: for every email, confirm the domain has a valid MX record
   (use `dig MX` / `nslookup` / a DNS library). Drop any domain with no MX.
5. Confidence rating: mark each "high" only if the address appears on an official
   company channel (career page, official Telegram, or job posting). Mark "medium"
   if inferred from pattern (e.g. careers@<domain> guessed). Exclude "low".
6. Output EXACTLY 100 rows in CSV with header:
   Company,Industry,City (KSA),Email,Source URL,Confidence,MX
   - Industry = the company's sector (e.g. Engineering, Retail, Healthcare, Logistics)
   - City (KSA) = HQ/operating city in KSA
   - Source URL = the exact URL the email was found at
   - Confidence = high | medium
   - MX = OK | FAIL
7. Do NOT fabricate. If you cannot verify an address, omit it and find another.
   Return only the CSV, no commentary.

RETURN THE 100-ROW CSV NOW.
```

---

## How to run this
- **Cheap/free:** paste into a web-search agent (e.g. the agent's web_extract on the
  Telegram t.me/s/* channels) or use Apify (already keyed) to scrape, then format CSV.
- **Verify before send:** once you have the CSV, run it through the same
  `quality_gate.py` + sent-log dedup we used for batch2 (0-overlap check) before
  adding to the sender queue.
- **Filename convention:** `autoapply-sa-hr-emails-100-batch3-YYYY-MM-DD.csv`

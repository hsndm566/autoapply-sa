# CV TAILORING ENGINE — spec

Per the operating standard: every application gets a tailored CV + cover letter. No generic submissions.

## For each job:
1. **Rewrite summary** to mirror the role (Industrial/Mechanical/etc.).
2. **Reorder + emphasize** relevant skills/experience from the client CV.
3. **Mirror JD keywords** (ATS keyword matching — Greenhouse hands to humans via scorecard; relevance > keyword stuffing).
4. **ATS-compatible formatting** — single column, standard headings, no tables/graphics that break parsers.
5. **Generate tailored cover letter** — 3-4 paras: hook + match + proof + CTA.

## Implementation (current orchestrator.py)
- `drafter_agent(desc, cv_text)` produces the tailored CV text using Groq/Zai/Gemini/OpenRouter chain.
- `reviewer_agent` (DeepSeek) scores + approves.
- `double_check` (Groq) is the second independent pass (the "someone double checks" requirement).
- Output saved as `app_{n}_{company}.txt` + logged to `Job_Application_Tracker.csv`.

## To add (backlog)
- True DOCX/PDF regeneration (currently text drafts; pdfplumber reads CV, need docx/writeback).
- RAG over CV (pranavvkumar21 pattern) for long CVs.
- Keyword extractor from JD → emphasis map.
- Cover-letter template库 per category.

## Client input
Only the client CV (PDF/txt/docx). Everything else generated. Intake via Telegram attachment (intake.py + vision_read.py for screenshots).

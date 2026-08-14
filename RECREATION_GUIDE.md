# 🚀 Autonomous Job Engine: Recreation Guide

This guide explains how to replicate the **AutoApply SA** system for a new candidate using only their CV.

---

## 📋 Phase 1: Fact Extraction & Profile Generation
**Input:** Candidate CV (PDF/DOCX)

1.  **Fact Extraction:** Use an LLM (like DeepSeek or GPT-4) to extract key facts from the CV:
    *   Full Name, Email, Phone.
    *   Location (City, Country).
    *   Education (Degree, University, Year).
    *   Experience (Roles, Companies, Dates).
    *   Skills & Keywords.
2.  **Profile Creation:** Save these facts into a standardized JSON file (`candidate_profile.json`). This becomes the "Source of Truth" for all applications.

---

## ⚙️ Phase 2: Governance Configuration
1.  **Ruleset:** Create a `candidate-profile.yaml` file to define the engine's boundaries:
    *   **Geography:** Which cities/countries are allowed?
    *   **Seniority:** Which levels are targeted (Entry, Junior, etc.)?
    *   **Portals:** Which sites to auto-apply vs. which to flag for review?
    *   **Safety:** Stop conditions (e.g., daily caps, budget limits).

---

## 🔍 Phase 3: Discovery & Scraper Integration
1.  **Search Engine:** Deploy scrapers (or use Google Search API) to find job links on targeted platforms:
    *   **Preferred:** Bayt.com, Jadeer, Taqat, LinkedIn.
    *   **Low-Friction:** Greenhouse, Ashby, Lever.
2.  **Deduplication:** Ensure the engine doesn't apply to the same role twice by maintaining a local SQLite database (`autoapply.db`).

---

## 🤖 Phase 4: The Auditor (Fact-Checking)
Before any application is submitted, an **Auditor Agent** must:
1.  Read the Job Description.
2.  Compare it against the `candidate_profile.json`.
3.  **Reject** if the candidate is unqualified (e.g., requires 10 years experience).
4.  **Approve** only if the facts align perfectly.

---

## 🚀 Phase 5: Submission & Self-Healing
1.  **Cloud Browser:** Use **Anchor Browser** to handle logins and bypass bot-detection.
2.  **Platform Adapters:** Write specialized Playwright scripts for each platform:
    *   `greenhouse_submit.py`
    *   `ashby_submit.py`
    *   `lever_submit.py`
3.  **Heartbeat Monitor:** A background script that checks the logs every 10 seconds. If a submission stalls, it kills the process and restarts the loop.

---

## ☁️ Phase 6: Cloud Deployment
1.  **GitHub:** Host the code for version control.
2.  **Railway:** Deploy the backend service for 24/7 persistence.
3.  **Persistence:** Mount a **Volume** on Railway to store the SQLite database and CV files so they survive restarts.

---

## 🛠️ Summary for a New User
To start a new candidate, you only need to:
1.  Upload their **CV**.
2.  Run the **Fact Extractor** script.
3.  Configure their **Geography & Seniority** in the YAML file.
4.  Deploy to **Railway**.

**The engine handles the rest.**

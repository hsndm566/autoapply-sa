# ENGINEERING BRIEF — AutoApply SA: broken per-industry personalization

## 1. What the system is supposed to do
A Python sender (`night_send_safe.py`) emails job applications to HR inboxes. For each recipient it must:
- Pick the **correct industry** from the recipient's domain/email.
- Attach the **CV PDF for that industry** (`cv_<industry>.pdf`, 14 variants exist: engineer, tech, retail, food, oil, construct, finance, health, logistics, manufactur, hospitality, chemical, beverage, supply).
- Write a **cover letter specific to that industry** (not a generic one).

## 2. What is actually happening (verified against 297 real sent emails in Gmail)
- **Cover letter is identical for every recipient.** Only the company name changes.
- **CV attachment is mismatched.** Example pulled live from Gmail:
  - TO: `careers@tamimiengineering.com` (an ENGINEERING company)
  - ATTACHED: `Hasan_Adam_CV_food.pdf`  ← food CV sent to an engineering firm
  - BODY says: *"My CV (tailored to engineer operations) is attached."*  ← contradicts the attachment
- 185 / 297 emails got `cv_engineer.pdf` (62%) — industry mapping defaults to "engineer" far too often.

## 3. Root cause (read the code)

### 3a. `draft()` generates ONE generic letter — the industry is never used in the body
```python
def draft(email):
    dom=email.split('@')[-1]; co=dom.split('.')[0].title(); ind=ind_for(email,dom)
    subj=f"Job Application – Industrial Engineer / Operations – {co}"
    body=(f"Dear {co} Hiring Team,\n\nI am an Industrial Engineer (BSc, UBT Jeddah) with logistics & operations "
          f"coordination at UBT, purchasing and vendor relations at Aljabr (Dammam), and Lean process optimization "
          f"(KAIA: 40% faster). I am interested in operations / industrial-engineering opportunities at {co}. "
          f"My CV (tailored to {ind} operations) is attached.\n\nBest regards,\n{NAME}\n{PHONE}\n{FROM}")
    return subj,body,ind
```
The variable `ind` is computed but **only interpolated as a string inside one fixed sentence** ("tailored to {ind} operations"). The actual prose, skills, and framing never change per industry. There is no industry-specific cover-letter template.

### 3b. Industry detection is keyword-only on the email string — weak and defaults to "engineer"
```python
IND_MAP=[("logistics","logistics"),("supply","supply"),("food","food"),("beverage","beverage"),("retail","retail"),
 ("hospitality","hospitality"),("chemical","chemical"),("manufactur","manufactur"),("construct","construct"),
 ("engineer","engineer"),("oil","oil"),("health","health"),("finance","finance"),("tech","tech")]

def ind_for(email,dom):
    blob=(email+dom).lower()
    for kw,ind in IND_MAP:
        if kw in blob: return ind
    return "engineer"   # <-- fallback catches everything that doesn't contain a keyword
```
Problems:
- Detection is done on the **email address + domain only**. A company like `tamimiengineering.com` contains "engineer" → maps correctly. But `careers@tamimiengineering.com` also contains "engineering" → should be engineer, yet in the live email it got `food`. That means the **real send path is not using `ind_for()` consistently** with what gets attached (see 3c).
- The `email_industry_map.json` (158 entries, loaded at runtime) is supposed to override `ind_for()`, but the mismatch in Gmail proves the override + the attachment selection disagree.

### 3c. Attachment selection vs letter claim can diverge
```python
def send(to,subj,body,ind):
    ...
    cvp=os.path.join(CVR,f"cv_{ind}.pdf")
    if not os.path.exists(cvp): cvp=os.path.join(CVR,"cv_engineer.pdf")   # silent fallback
    ...
    msg.add_attachment(data,maintype="application",subtype="pdf",filename=f"Hasan_Adam_CV_{ind}.pdf")
```
`ind` passed to `send()` comes from `draft()`'s `ind_for()` result. But the **caller in the main loop** does:
```python
s,b,_=draft(em)
ind=IND_MAP_JSON.get(em, ind_for(em,dom))   # precise map, fallback to keyword
ok,verdict=ds_factcheck(s,b,ind)
if not ok: ... continue
ok2,st=send(em,s,b,ind)
```
So `ind` CAN be recomputed between `draft()` and `send()` (via `IND_MAP_JSON`). If `IND_MAP_JSON[em]` returns "food" but `draft()` wrote the letter for "engineer", the **letter and attachment disagree** — exactly what we see in Gmail. The letter is always engineer-shaped; the attachment follows whatever `IND_MAP_JSON` says.

### 3d. The quality gate does not catch this
`ds_factcheck()` only checks *"is the CV factually consistent with the real CV facts?"* — it does NOT check *"does the cover letter match the recipient's industry?"* So a generic engineer letter + a food CV passes the gate.

## 4. The fix we need (hand to dev)
We need the cover letter to be **genuinely per-industry**, and the industry → CV mapping to be **single-source and consistent** end-to-end. Specifically:
1. **One deterministic `resolve_industry(email, dom)`** used everywhere (draft, attachment, log). No recomputation that can diverge. `email_industry_map.json` is the source of truth; keyword fallback only if absent; never silently fall back to "engineer" unless truly unknown.
2. **Per-industry cover-letter templates** (or an LLM call that receives the industry + the industry CV's real bullet points and writes a letter framed for that sector). The letter must name the sector's relevant skills (e.g., food → HACCP/FSMS/supply-chain cold chain; finance → controls/reporting; health → compliance/patient ops).
3. **Consistency assertion before send**: assert `attached_cv_industry == letter_industry == resolved_industry`, else block.
4. Keep the existing `verify_cv()` + `quality_gate` gates; extend the fact-check prompt to also reject "letter industry ≠ attachment industry."

## 5. Acceptance test (must pass before we deploy)
For a sampled set of recipients across all 14 industries, the sent email must show:
- attachment filename `Hasan_Adam_CV_<ind>.pdf` where `<ind>` matches the recipient's real sector,
- cover letter body references that sector's specific skills,
- `resolved_industry` logged once and identical in letter + attachment + log.

## 6. Files
- `C:/Users/hasan/Desktop/clients/system/night_send_safe.py` (sender; `draft`, `ind_for`, `send`, main loop)
- `C:/Users/hasan/Desktop/clients/system/email_industry_map.json` (158-entry override map)
- `C:/Users/hasan/Desktop/clients/system/cv_variants/cv_*.pdf` (14 CVs)
- `C:/Users/hasan/Desktop/clients/system/quality_gate.py` (gate; extend fact-check)

## 7. Constraints
- No new paid services. LLM call (DeepSeek) already available; can be reused to generate the per-industry letter.
- Must keep running on Railway (Python, no Chromium needed).
- Do NOT send any emails during the fix. Verification is by reading the generated letter + attachment filename locally, and by re-checking a sample of already-sent Gmail messages after deploy (with user approval).

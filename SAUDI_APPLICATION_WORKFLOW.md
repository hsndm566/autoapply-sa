# Saudi Application Workflow Handoff

This document summarizes the successful, Saudi-relevant application route and the resilient automation patterns discovered during the controlled submission for Hassan Adam on Aug 12, 2026.

## 1. Successful Route Summary

| Employer | Role | Location | Portal | Outcome |
| --- | --- | --- | --- | --- |
| **Nash** | Logistics Product Manager, MENA | Saudi Arabia / UAE | **Ashby** | **Success** |

### **Key findings from the Nash/Ashby route:**
- **Automation Friendly:** No bot detection, CAPTCHA, or login barriers were encountered during the live submission.
- **CV Upload:** The portal supports a standard hidden `input[type="file"]` that can be exposed and interacted with reliably.
- **Factual Integrity:** The form required only Name, Email, and CV, minimizing the risk of inventing candidate data.
- **Tailored Outreach:** The tailored cover comment was independently approved by the Auditor, ensuring no unsupported claims were made.

## 2. Failed Route Analysis (BEC Arabia)

| Employer | Role | Location | Portal | Outcome |
| --- | --- | --- | --- | --- |
| **BEC Arabia** | Logistics Coordinator | Neom, Saudi Arabia | Custom / Public | **Blocked** |

### **Blocker details:**
- **Bot Detection:** The final submission click was rejected with a "Bot detection failed" error. This is a common safeguard on custom employer portals.
- **Manual Handoff:** In such cases, the agent should prepare the form (attach CV, fill fields) and then hand over the browser to the human user for the final click and CAPTCHA solution.

## 3. Recommended Saudi-Relevant Strategy

To achieve high-volume, high-success applications in the Saudi market:

1. **Prioritize Proven ATS Portals:**
   - **Ashby:** Highly reliable, low barrier, supports CV upload proof.
   - **Greenhouse:** Generally reliable, but may require more factual candidate data (nationality, relatives, salary).
   - **Lever:** Reliable, but often requires a brief candidate comment/cover letter.

2. **Auditor-Gated Tailoring:**
   - Always run an independent Auditor review for any role-specific comment or cover letter to ensure zero hallucination or overstatement of candidate facts.

3. **Hybrid Automation for Custom Portals:**
   - Use the agent to discover, verify, and prepare the form.
   - If bot detection is encountered, use the `take_over_browser` protocol for the final submission.

## 4. Operational Readiness

The platform is now proven to:
- **Identify** Saudi-relevant roles using candidate CV facts.
- **Verify** application routes read-only before any action.
- **Audit** the truthfulness of the application package.
- **Submit** successfully to modern ATS portals (Ashby) while capturing evidence.

This workflow is ready to be integrated into the autonomous campaign worker for scaled outreach.

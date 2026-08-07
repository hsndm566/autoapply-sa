# INTERVIEW MODE — the moment a response asks for an interview

_Triggered by `trigger_interview()` the instant a response requests an interview. The engine switches from applicant to strategist._

## What it does (within 1 hour of confirmation)
1. **Company research** — news, funding, leadership, tech stack, Glassdoor, competitors (free web, API-first).
2. **Full brief** saved to `/clients/[name]-interview-prep/[company].md`:
   - 5 likely interview questions (role + company type)
   - STAR-format answers **tailored to the client's real CV**
   - Salary negotiation range (pulled from `salary-intelligence.md` map)
   - 1 smart strategic question to ask the interviewer
   - Red flags to PROBE during the interview
3. **Delivered to Telegram** (chunked) immediately.

## Trigger
`log_response` with an interview-confirmed status, or any inbound "interview" message → `trigger_interview(client, company, role, cv_text)`.

## Why
The application got past the algorithm. Now the client needs to win the human. The brief turns raw company signal into a prepared, confident candidate — anchored on their real experience and the salary map.

## Last brief

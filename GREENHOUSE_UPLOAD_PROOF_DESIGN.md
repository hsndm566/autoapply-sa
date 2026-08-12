# Greenhouse Upload-Proof Adapter Design

**Purpose.** This adapter establishes a narrow, source-specific proof that a selected CV file was attached through a Greenhouse-hosted application form and that a post-submit confirmation was observed. It is deliberately not a general application bot. It does not discover jobs, draft content, invent answers, solve CAPTCHAs, bypass login, or enable legacy external execution.

## Evidence model

| Proof stage | Required evidence | Effect |
| --- | --- | --- |
| `upload_selected` | A visible Greenhouse `input[type=file]`, the selected file name, the locally computed CV SHA-256, and a form fingerprint | Demonstrates a file-selection operation only; never permits a submission. |
| `submitted_confirmed` | All upload evidence plus a distinct post-submit URL or a recognised confirmation message and its digest | May be presented to the Auditor as source-specific evidence, but does not independently approve an application. |
| `blocked` | A precise reason such as missing file control, mandatory unmapped question, CAPTCHA/login, no explicit authority, or no confirmation signal | Stops the route with no silent fallback. |

## Control boundaries

The implementation accepts a browser-driver abstraction so that deterministic, offline tests can simulate the lifecycle without a live candidate or job board. The production service leaves its live-execution switch off. Any future live browser driver must only be invoked after: (1) a valid campaign CV has been integrity-checked, (2) the application package carries a current Auditor approval, (3) the job-specific required fields are explicitly mapped, and (4) a separate source-level activation decision is recorded. It must stop on CAPTCHA, login, unknown mandatory questions, duplicate-application warnings, or missing confirmation evidence.

## Source rationale

Greenhouse documents that application questions are job-specific and that a required Resume question can accept a `resume` file input; it also explicitly supports multipart direct resume upload and warns that client-side validation of required fields is necessary.[1] Its candidate-upload support page lists `.doc`, `.docx`, `.pdf`, `.rtf`, and `.txt` as accepted document types, with a 100 MB limit.[2] The AutoApply adapter is intentionally more restrictive than that vendor limit because its campaign API currently limits uploaded CVs to the formats and size configured by the service.

## References

[1]: https://developers.greenhouse.io/job-board.html "Greenhouse Job Board API"
[2]: https://support.greenhouse.io/hc/en-us/articles/360052218132-Supported-formats-for-resumes-cover-letters-and-other-candidate-uploads "Greenhouse supported candidate uploads"

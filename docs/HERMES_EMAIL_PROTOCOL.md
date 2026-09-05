# Hermes Application Protocol

## Operating mode

Hermes may research public opportunities and prepare grounded application drafts.

Hermes may not send an email, submit a portal form, manufacture approval, solve a CAPTCHA, or claim an application was submitted without verified evidence.

The enforced lifecycle is:

```text
discovered
→ normalized
→ path_verified
→ drafted
→ human approved
→ submission attempted
→ submitted_verified
```

A draft or review-queue entry is not an application submission.

## Candidate data

Candidate identity, CV files, contact details, and account-specific preferences must come from the private campaign datastore or private runtime storage.

Do not place candidate names, phone numbers, private email addresses, CV file contents, CV paths, credentials, or customer profiles in this repository.

Do not invent employers, dates, degrees, certifications, years of experience, licenses, salary expectations, nationality, work authorization, achievements, or skills.

## Human approval

Every employer-facing application requires an explicit human approval tied to the exact draft.

The approver identity must come from authenticated server-side context. Never accept an `approved_by` identity from a request body.

Approval must be integrity-bound to the exact source, posting id, subject, cover letter, approver, and approval timestamp. Editing approved content invalidates the approval.

## Email lane

Employer email must use the audited durable email dispatcher.

Before transport the dispatcher must verify:

- a current human approval record
- matching approval integrity digest
- current Auditor approval
- exact destination and approved message content
- exactly one valid PDF CV attachment
- an authorized sender identity from private deployment configuration
- duplicate protection

A successful transport outcome requires provider evidence such as an SMTP Message-ID or transactional-provider message id.

A transport timeout or ambiguous provider result becomes `uncertain`. It must not be retried automatically.

## Portal lane

Portal submission may run only for a record classified `portal_upload_verified` and already in `audit_approved`.

The adapter must recheck the shared approval gate before browser navigation or any final employer-facing action.

CAPTCHA, login, OTP, anti-bot controls, unsupported questions, missing CV upload, or ambiguous final confirmation must stop automation and become a human handoff or review hold.

Do not bypass CAPTCHA or anti-bot controls.

A portal result becomes `submitted_verified` only after concrete post-submit evidence is observed, such as a confirmation page, confirmation id, verified success marker, or equivalent defensible proof.

## Drafting rules

Use only facts present in the candidate profile supplied by the private campaign context.

If a required qualification is not evidenced, record it as a gap rather than implying the candidate has it.

Grounded evidence and CV highlights must be checked against the candidate profile before a draft can enter review.

## Recipient and opportunity verification

Prepare applications only for a real company and role supported by a current source.

For email applications, the recipient must be supported by an employer or recruiter source. Do not use guessed, purchased, scraped-without-verification, or unrelated addresses.

For portals, preserve the exact source URL and posting identity.

## Evidence and audit

Persist state changes and submission evidence in the campaign datastore.

Audit metadata may include:

- campaign and job identifiers
- source
- state before and after
- actor
- approval digest
- timestamp
- adapter or channel
- refusal reason
- evidence keys

Do not log CV text, cover-letter contents, passwords, API keys, authentication tokens, or private candidate contact details.

## Duplicate protection

A `submitted_verified` record cannot be submitted again.

An uncertain result cannot be retried automatically. A human must review the evidence and explicitly choose the next action.

## Repository rule

The repository contains application code and synthetic test fixtures only.

Runtime databases, candidate profiles, CV files, recipient exports, contact histories, tracking files, and private campaign data belong outside Git.

# FREE ATS APIs — exact endpoints (verified 2026-08-07)

All return structured JSON. No API key, no browser. This is the backbone of the engine — highest quality, $0 cost.

## Greenhouse
```
GET https://boards-api.greenhouse.io/v1/boards/{company_token}/jobs?content=false
# list companies: https://boards-api.greenhouse.io/v1/boards/{token}/jobs
# single job: .../jobs/{id}
# custom fields + questions: content=true
```
Verified: `anthropic` returned live jobs. Rate limit ~fair; respect 1 req/sec.

## Lever
```
GET https://api.lever.co/v0/postings/{company}?mode=json&limit=100
# commits=true for departments; location filter via ?location=
```
Verified: `stitch` returned live jobs.

## Ashby (GraphQL)
```
POST https://jobs.ashbyhq.com/api/non-user-graphql
{ "query": "{ jobBoard(jobBoardHost: \"{company}.ashbyhq.com\") { jobs { id title location { name } } } }" }
```
Verified: `linear.ashbyhq.com` returned live jobs.

## Workable
```
GET https://apply.workable.com/api/v3/accounts/{company}/jobs
# requires no key for public boards; some need ?access_key=
```

## SmartRecruiters
```
GET https://api.smartrecruiters.com/v1/companies/{company}/postings
```

## BambooHR
```
GET https://{company}.bamboohr.com/careers/list
```

## Discovery trick (find a company's ATS)
1. Visit `company.com/careers` → look for "Powered by Greenhouse/Lever/Ashby"
2. Or grep the page HTML for `boards.greenhouse.io`, `jobs.lever.co`, `ashbyhq.com`
3. Extract the slug → call the API directly

## Free proxy (one-liner)
```
curl https://jobber.mihir.ch/greenhouse/anthropic
curl https://jobber.mihir.ch/lever/stitch
curl https://jobber.mihir.ch/ashby/linear
```

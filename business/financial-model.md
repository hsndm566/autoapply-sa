# FINANCIAL MODEL — this is a business, not a script

_Auto-updated every Sunday by `business_model.py`. The owner needs to know exactly when this pays them a salary._

## Pricing (SAR/mo per client)
- Basic: 49
- Pro: 129
- Enterprise: 399

## Weekly computes
- Total applications (all clients)
- Estimated interview rate (from logged responses)
- Revenue/client at current tier
- Cost/application (compute + time)
- Projected monthly revenue at current volume
- 3 scenarios: current / 2x / 10x — what breaks, what changes, revenue
- **Salary breakpoint**: clients needed to pay the owner (target 5000 SAR/mo)

## Scenarios logic
`scenario(clients)` = clients × apps/client × tier price − compute cost. The model
flags what breaks at 2x (CI fine) and 10x (need Azure VM, proxy pool, 2nd key;
human approval steps become the bottleneck).

## Reports

## 2026-08-07 — WEEKLY BUSINESS HEALTH
- Applications (all clients): 1 | Clients: 1
- Responses: 1 | Est. interview rate: 100.0%
- Revenue/client (pro): 129 SAR/mo

### Scenarios (pro tier, 1 apps/client)
- **CURRENT**: clients=1, apps=10, revenue=129 SAR, cost=1 SAR, net=128 SAR, pays-owner=False
  - breaks: Nothing — single machine handles it.
- **2X**: clients=2, apps=20, revenue=258 SAR, cost=2 SAR, net=256 SAR, pays-owner=False
  - breaks: GitHub Actions free tier still fine; local load doubles but OK.
- **10X**: clients=10, apps=100, revenue=1290 SAR, cost=8 SAR, net=1282 SAR, pays-owner=False
  - breaks: Need Azure VM (or more CI minutes), proxy pool for scraping, maybe a 2nd Groq key. Human approval steps (Jadarat, LinkedIn post) become the bottleneck — automate or delegate.

### SALARY BREAKPOINT
- Target: 5000 SAR/mo

## 2026-08-07 — WEEKLY BUSINESS HEALTH
- Applications (all clients): 1 | Clients: 1
- Responses: 1 | Est. interview rate: 100.0%
- Revenue/client (pro): 129 SAR/mo

### Scenarios (pro tier, 1 apps/client)
- **CURRENT**: clients=1, apps=10, revenue=129 SAR, cost=1 SAR, net=128 SAR, pays-owner=False
  - breaks: Nothing — single machine handles it.
- **2X**: clients=2, apps=20, revenue=258 SAR, cost=2 SAR, net=256 SAR, pays-owner=False
  - breaks: GitHub Actions free tier still fine; local load doubles but OK.
- **10X**: clients=10, apps=100, revenue=1290 SAR, cost=8 SAR, net=1282 SAR, pays-owner=False
  - breaks: Need Azure VM (or more CI minutes), proxy pool for scraping, maybe a 2nd Groq key. Human approval steps (Jadarat, LinkedIn post) become the bottleneck — automate or delegate.

### SALARY BREAKPOINT
- Target: 5000 SAR/mo
- Clients needed NOW: 38.8 (currently CANNOT pay owner)

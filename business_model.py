#!/usr/bin/env python3
"""business_model.py — weekly business health + financial model.

Not just applications — this is a BUSINESS. Every week compute:
  - total applications across all clients
  - estimated interview rate (from logged responses)
  - revenue per client at current pricing (49/129/399 SAR tiers)
  - cost per application (compute + time)
  - projected monthly revenue at current client volume
  - 3 scenarios: current / 2x / 10x volume -> what breaks, what changes, revenue
  - SALARY BREAKPOINT: exactly when the business can pay the owner a salary

Model saved to /business/financial-model.md, updated automatically every Sunday.
"""
import os, json, datetime, csv, collections

BASE = os.path.dirname(os.path.abspath(__file__))
FIN = os.path.join(BASE, "business", "financial-model.md")
TRACKER = os.path.join(BASE, "Job_Application_Tracker.csv")

# Pricing (SAR/mo per client tier) — from the hsndm.tech storefront spec
PRICING = {"basic": 49, "pro": 129, "enterprise": 399}
DEFAULT_TIER = "pro"  # assume most clients on pro tier unless known
# Owner salary target (SAR/mo) — the breakpoint goal
OWNER_SALARY_TARGET = 5000  # SAR/mo (~$1333) — adjustable

# Cost model (per application)
COMPUTE_COST_PER_APP = 0.02   # USD equiv in Groq/API calls
TIME_COST_PER_APP = 0.0       # automated; human time ~0 after setup


def _aggregate():
    """Read tracker (PII-light: counts only) -> totals + interview rate."""
    apps = 0
    responses = 0
    clients = set()
    interviews = 0
    try:
        for row in csv.DictReader(open(TRACKER, encoding="utf-8")):
            apps += 1
            clients.add(row.get("Client", "?"))
            if row.get("Response Date", "").strip():
                responses += 1
            if "interview" in (row.get("Status", "") + row.get("Response Date", "")).lower():
                interviews += 1
    except Exception:
        pass
    interview_rate = (responses / apps) if apps else 0
    return {"apps": apps, "responses": responses, "clients": len(clients),
            "interviews": interviews, "interview_rate": interview_rate}


def scenario(clients_n, apps_per_client=10, tier=DEFAULT_TIER):
    """Model one volume scenario. Returns revenue/cost/breakpoint dict."""
    apps = clients_n * apps_per_client
    revenue_sar = clients_n * PRICING[tier]
    cost_usd = apps * COMPUTE_COST_PER_APP
    cost_sar = cost_usd * 3.75  # USD->SAR rough
    net_sar = revenue_sar - cost_sar
    can_pay = net_sar >= OWNER_SALARY_TARGET
    clients_to_salary = (OWNER_SALARY_TARGET + cost_sar) / PRICING[tier] if PRICING[tier] else 0
    return {
        "clients": clients_n, "apps": apps, "revenue_sar": round(revenue_sar),
        "cost_sar": round(cost_sar), "net_sar": round(net_sar),
        "can_pay_owner": can_pay,
        "clients_needed_for_salary": round(clients_to_salary, 1),
    }


def weekly_report():
    """Build the full weekly business health report."""
    agg = _aggregate()
    cur = scenario(agg["clients"] or 1)
    x2 = scenario((agg["clients"] or 1) * 2)
    x10 = scenario((agg["clients"] or 1) * 10)
    # what breaks at each level
    breaks = {
        "current": "Nothing — single machine handles it.",
        "2x": "GitHub Actions free tier still fine; local load doubles but OK.",
        "10x": "Need Azure VM (or more CI minutes), proxy pool for scraping, "
               "maybe a 2nd Groq key. Human approval steps (Jadarat, LinkedIn post) "
               "become the bottleneck — automate or delegate.",
    }
    report = {
        "date": datetime.date.today().isoformat(),
        "aggregate": agg,
        "scenarios": {"current": cur, "2x": x2, "10x": x10},
        "breaks": breaks,
        "salary_breakpoint": {
            "target_sar": OWNER_SALARY_TARGET,
            "clients_needed_now": cur["clients_needed_for_salary"],
            "can_pay_now": cur["can_pay_owner"],
        },
    }
    _save_doc(report)
    return report


def _save_doc(r):
    os.makedirs(os.path.dirname(FIN), exist_ok=True)
    with open(FIN, "a", encoding="utf-8") as f:
        f.write(f"\n## {r['date']} — WEEKLY BUSINESS HEALTH\n")
        a = r["aggregate"]
        f.write(f"- Applications (all clients): {a['apps']} | Clients: {a['clients']}\n")
        f.write(f"- Responses: {a['responses']} | Est. interview rate: {a['interview_rate']*100:.1f}%\n")
        f.write(f"- Revenue/client (pro): {PRICING[DEFAULT_TIER]} SAR/mo\n")
        f.write(f"\n### Scenarios (pro tier, {a['apps']//max(a['clients'],1)} apps/client)\n")
        for k in ("current", "2x", "10x"):
            s = r["scenarios"][k]
            f.write(f"- **{k.upper()}**: clients={s['clients']}, apps={s['apps']}, "
                    f"revenue={s['revenue_sar']} SAR, cost={s['cost_sar']} SAR, "
                    f"net={s['net_sar']} SAR, pays-owner={s['can_pay_owner']}\n")
            f.write(f"  - breaks: {r['breaks'][k]}\n")
        sb = r["salary_breakpoint"]
        f.write(f"\n### SALARY BREAKPOINT\n")
        f.write(f"- Target: {sb['target_sar']} SAR/mo\n")
        f.write(f"- Clients needed NOW: {sb['clients_needed_now']} "
                f"(currently {'CAN' if sb['can_pay_now'] else 'CANNOT'} pay owner)\n")


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(weekly_report(), indent=2, default=str))

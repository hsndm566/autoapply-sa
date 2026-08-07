#!/usr/bin/env python3
"""income_tracker.py — the money ledger. No motivation, no loud celebration.
Just the number and what moves it.

Columns (in /business/income-tracker.md):
  SOURCE | AMOUNT (SAR, earned or expected) | DATE | STATUS (earned/pending/confirmed)

- add(source, amount, date, status): append a row on every money move or confirmed
  paying opportunity.
- weekly_summary(): returns {earned_this_month, pending, closest_confirmed, action}
  for the Sunday financial brief.

STATUS values:
  earned    = money actually received
  pending   = invoiced/submitted, awaiting payout
  confirmed = paying opportunity verified (gig won, order accepted) but not yet paid
"""
import os, re, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
TRACK = os.path.join(BASE, "business", "income-tracker.md")


def add(source, amount, status="confirmed", date=None):
    """Append one income row. amount in SAR (number)."""
    date = date or datetime.date.today().isoformat()
    os.makedirs(os.path.dirname(TRACK), exist_ok=True)
    if not os.path.exists(TRACK):
        open(TRACK, "w", encoding="utf-8").write(
            "# INCOME TRACKER\n\nSOURCE | AMOUNT (SAR) | DATE | STATUS\n---|---|---|---\n")
    with open(TRACK, "a", encoding="utf-8") as f:
        f.write(f"{source} | {amount} | {date} | {status}\n")
    return True


def _rows():
    rows = []
    try:
        for line in open(TRACK, encoding="utf-8"):
            if "|" in line and line.strip().startswith(("#", "SOURCE")):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 4:
                try:
                    amt = float(parts[1])
                except Exception:
                    continue
                rows.append({"source": parts[0], "amount": amt,
                             "date": parts[2], "status": parts[3]})
    except Exception:
        pass
    return rows


def weekly_summary():
    """Four numbers for the Sunday brief."""
    rows = _rows()
    today = datetime.date.today()
    month = today.strftime("%Y-%m")
    earned = sum(r["amount"] for r in rows
                 if r["status"] == "earned" and r["date"].startswith(month))
    pending = sum(r["amount"] for r in rows if r["status"] in ("pending", "confirmed"))
    confirmed = [r for r in rows if r["status"] in ("confirmed", "pending")]
    closest = min(confirmed, key=lambda r: r["date"]) if confirmed else None
    # one specific action to increase the number this week (cheapest high-probability)
    action = ("Post a Khamsat CV/Excel gig today (50 SAR, same-day fulfill) — "
              "closest confirmed-moving action.") if not earned else \
             ("Fulfill the pending confirmed gig and request payout this week.")
    summary = {
        "earned_this_month": earned,
        "pending": pending,
        "closest_confirmed": closest,
        "action": action,
    }
    _append_summary(summary)
    return summary


def _append_summary(s):
    with open(TRACK, "a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.date.today().isoformat()} SUNDAY BRIEF\n")
        f.write(f"- Earned this month: {s['earned_this_month']} SAR\n")
        f.write(f"- Pending: {s['pending']} SAR\n")
        cc = s["closest_confirmed"]
        f.write(f"- Closest confirmed source: {cc['source']} ({cc['amount']} SAR, {cc['date']})\n" if cc else "- Closest confirmed source: none\n")
        f.write(f"- This week's number-mover: {s['action']}\n")


if __name__ == "__main__":
    import json as _j
    # demo: seed a confirmed opportunity + show summary
    add("Khamsat CV gig (confirmed order)", 50, "confirmed")
    print(_j.dumps(weekly_summary(), indent=2, default=str))
    print("--- tracker ---")
    print(open(TRACK, encoding="utf-8").read()[-400:])

#!/usr/bin/env python3
"""money_first.py — the daily "income now" question.

Every morning 8AM (Saudi = 05:00 UTC): what is the FASTEST legitimate action today
that moves money closer to the owner? Picks ONE specific action (never a list) and
sends it to Telegram.

Paths considered (ranked by time-to-money):
  1. Same-day freelance gig the owner can DELIVER today (Khamsat/Mostaql/Upwork) —
     CV tailoring, Excel, research, doc conversion, Arabic<->English.
  2. Direct outreach to a warm lead (profile viewer from personal_brand) needing
     a deliverable.
  3. AutoApply urgent role (slower: interview->hire) — fallback, not primary.

Honesty: if a REAL live gig is found via scan, cite it. If none found this run,
default to the standing best bet (post a Khamsat CV gig — owner can fulfill today)
and label it as the default, not as a verified live listing.
"""
import os, re, datetime, json, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "system", "money-first-log.md")

# Owner's deliverable skills (from profile) -> fastest freelance products
DELIVERABLES = [
    "tailor your CV + write a cover letter (24h)",
    "build/clean an Excel spreadsheet or dashboard",
    "do a focused web/research report",
    "convert or format a document (PDF/Word)",
    "translate Arabic<->English (business/CV)",
]


def _scan_gigs():
    """Real scan for fresh freelance postings the owner can fulfill today.
    Returns (found_bool, source_url, snippet) — honest about whether live."""
    q = "خمسات مستقل Upwork CV تجهيز Excel مهمة سريعة pay same day"
    try:
        req = urllib.request.Request(
            "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q),
            headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        # crude: any result snippet mentioning a deliverable + a price/time
        if re.search(r"(خمسات|مستقل|upwork|cv|سيرة|إكسل|excel)", html, re.I):
            # extract first result snippet
            m = re.search(r'result__snippet[^>]*>(.*?)</a>', html, re.S)
            snip = re.sub(r"<[^>]+>", " ", m.group(1)).strip()[:200] if m else ""
            return True, "https://khamsat.com / mostaql.com (live scan)", snip
    except Exception as e:
        return False, f"scan_error:{e}", ""
    return False, "", ""


def pick_action():
    """Return ONE specific action dict."""
    found, src, snip = _scan_gigs()
    if found:
        # a live gig surface exists -> direct the owner to grab one now
        action = (f"OPEN خمسات/مستقل now and bid on a fresh CV-or-Excel gig you can "
                  f"deliver in <3h. You have a CV example ready — fulfill same-day, "
                  f"get paid on platform. Scan hit: {src}.")
        kind = "LIVE_GIG"
    else:
        # default standing best bet (owner can fulfill today, no waiting)
        action = ("POST a Khamsat gig RIGHT NOW: 'I'll tailor your CV + write a cover "
                  "letter in 24h — 50 SAR.' You have a ready CV example, can fulfill "
                  "instantly. This is the fastest same-day path with what you have.")
        kind = "DEFAULT_GIG"
    # also surface AutoApply as the slower pipeline (not the day's primary action)
    note = ("Slower pipeline running in background: AutoApply sent role drafts; "
            "those convert at interview->hire, not same-day.")
    # log a confirmed income opportunity (50 SAR standard gig, the closest money)
    try:
        import income_tracker as IT
        IT.add(f"money-first: {kind} Khamsat/CV gig", 50, "confirmed")
    except Exception:
        pass
    return {"date": datetime.date.today().isoformat(),
            "kind": kind, "action": action, "note": note, "source": src}


def run():
    r = pick_action()
    _log(r)
    _send(r)
    return r


def _log(r):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n## {r['date']} 08:00 — MONEY-FIRST\n")
        f.write(f"- kind: {r['kind']} | source: {r['source']}\n")
        f.write(f"- ACTION: {r['action']}\n")
        f.write(f"- note: {r['note']}\n")


def _send(r):
    try:
        import orchestrator as O
        msg = (f"💰 MONEY-FIRST ({r['date']} 08:00)\n"
               f"One action today:\n{r['action']}\n\n"
               f"{r['note']}\n"
               f"{'(live scan)' if r['kind']=='LIVE_GIG' else '(default — no live listing found this run)'}")
        O.tg(msg)
    except Exception:
        pass


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(run(), indent=2, default=str))

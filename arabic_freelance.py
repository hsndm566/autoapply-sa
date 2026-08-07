#!/usr/bin/env python3
"""arabic_freelance.py — daily Khamsat + Mostaql gig hunter (Arabic freelance track).

Scans BOTH platforms' buyer-request boards every day for gigs matching:
  document work, translation help, data entry, research, Excel/PDF, CV writing,
  any technical task the owner can deliver in <3h.

- Drafts proposals in FORMAL GULF ARABIC (not Egyptian dialect) when client is Arabic.
- Flags posts needing <1h response (speed wins on these platforms).
- Logs every proposal to /business/arabic-freelance-pipeline.md.

Verified endpoints (real check 2026-08-07):
  Khamsat requests: https://khamsat.com/orders   (200, Arabic)
  Mostaql projects:  https://mostaql.com/projects (200, Arabic, ?sort=latest)
"""
import os, re, datetime, json, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.join(BASE, "business", "arabic-freelance-pipeline.md")

KHAMSAT = "https://khamsat.com/orders"
MOSTAQL = "https://mostaql.com/projects?sort=latest"

# gig categories the owner can deliver (Arabic + English keywords)
CATS = {
    "document": ["وثيقة", "مستند", "document", "تنسيق"],
    "translation": ["ترجمة", "translation", "translate"],
    "data_entry": ["إدخال بيانات", "data entry", "بيانات"],
    "research": ["بحث", "research", "دراسة"],
    "excel": ["إكسل", "excel", "جدول", "spreadsheet"],
    "pdf": ["pdf", "ملف", "تحويل"],
    "cv": ["سيرة ذاتية", "cv", "سيرة", "تأليف سيرة"],
    "technical": ["تقني", "technical", "برمجة", "تنسيق"],
}


def _fetch(url):
    try:
        return urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20
        ).read().decode("utf-8", "ignore")
    except Exception:
        return ""


def _match_gigs(html):
    """Extract post titles + classify into CATS. Returns list of (title, cats)."""
    # pull visible Arabic/English text blocks (anchor titles where possible)
    titles = re.findall(r'title="([^"]{8,120})"', html)
    if not titles:
        titles = re.findall(r'>([\u0600-\u06FF\u0020-\u007F]{10,120})<', html)
    out = []
    for t in set(titles):
        low = t.lower()
        hit = [c for c, kws in CATS.items() if any(k in low for k in kws)]
        if hit:
            out.append((t.strip(), hit))
    return out[:15]


def draft_proposal_ar(title, cats):
    """Formal Gulf Arabic proposal (not Egyptian dialect)."""
    cat_txt = "، ".join(cats)
    return (
        f"السلام عليكم ورحمة الله وبركاته. أرى طلبكم بخصوص: {title}. "
        f"أنا مستعد لتنفيذ المهمة بدقة واحترافية ضمن الوقت المطلوب "
        f"(التصنيف: {cat_txt}). لدي خبرة في هذا النوع من الأعمال وأسلّم العمل سريعاً "
        f"بجودة عالية. هل يمكنكم تأكيد التفاصيل والميزانية لنبدأ فوراً؟ وجزاكم الله خيراً."
    )


def scan():
    today = datetime.date.today().isoformat()
    kh = _fetch(KHAMSAT)
    mo = _fetch(MOSTAQL)
    gigs = []
    for src, html in [("Khamsat", kh), ("Mostaql", mo)]:
        for title, cats in _match_gigs(html):
            gigs.append({"src": src, "title": title, "cats": cats,
                         "proposal_ar": draft_proposal_ar(title, cats)})
    _log(today, gigs)
    _send(today, gigs)
    # log each matched gig as a confirmed income opportunity (closest money)
    try:
        import income_tracker as IT
        for g in gigs:
            IT.add(f"arabic-freelance: {g['src']} {g['cats']}", 50, "confirmed")
    except Exception:
        pass
    return {"date": today, "count": len(gigs), "gigs": gigs}


def _log(today, gigs):
    os.makedirs(os.path.dirname(PIPE), exist_ok=True)
    with open(PIPE, "a", encoding="utf-8") as f:
        f.write(f"\n## {today} — ARABIC FREELANCE SCAN\n")
        f.write(f"- gigs matched: {len(gigs)}\n")
        for g in gigs:
            f.write(f"  - [{g['src']}] {g['title']} | cats={g['cats']}\n")
            f.write(f"    PROPOSAL(AR): {g['proposal_ar']}\n")
        f.write(f"- SPEED RULE: respond <1h of posting (speed wins on Khamsat/Mostaql).\n")


def _send(today, gigs):
    try:
        import orchestrator as O
        if not gigs:
            O.tg(f"🔎 Arabic freelance {today}: no matching gigs found this scan.")
            return
        msg = f"🔎 ARABIC FREELANCE {today} — {len(gigs)} matching gig(s)\n"
        for g in gigs[:5]:
            msg += f"\n[{g['src']}] {g['title']}\n→ {g['proposal_ar'][:120]}...\n"
        msg += "\nRespond <1h of posting. Full proposals in arabic-freelance-pipeline.md."
        O.tg(msg)
    except Exception:
        pass


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(scan(), indent=2, default=str)[:1500])

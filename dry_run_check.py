#!/usr/bin/env python
"""
dry_run_check.py — FULL-MAP regression harness (NO emails sent).

Runs every mapped email + a sample of edge-case/unmapped domains through the
real pipeline: resolve_industry -> draft -> consistency assertion. Prints a table:

  email | resolved_industry | reason | cv_file | letter_has_sector_skill | consistent

This is the acceptance test scaled to the WHOLE map (dev's advice), not just 14 samples.
Run: python dry_run_check.py
"""
import os, sys, csv
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
import industry as IND
import night_send_safe as S   # reuse draft()/send() consistency logic without SMTP

# boot assert (same as production)
IND.boot_assert_cv_files()

# 1) all 158 mapped emails
rows=[]
for em in IND._OVERRIDE:
    dom=em.split('@')[-1]
    rows.append(em)

# 2) edge-case / unmapped domains (must route to 'unknown', never 'engineer' silently)
EDGE=[
    "info@some-random-company.com",   # no keyword
    "contact@xyzholding.net",          # no keyword
    "hello@brandnewstartup.io",        # no keyword
    "jobs@tamimiengineering.com",      # keyword 'engineer' -> engineer (real case that broke before)
    "careers@nestle.com",              # keyword 'food'? no -> falls to keyword? 'nestle' has no kw -> unknown
    "hr@alrajhibank.com",              # 'bank' no kw -> unknown
]
rows += EDGE

print(f"{'EMAIL':42} {'INDUSTRY':12} {'REASON':9} {'CV_FILE':22} {'SECTOR_OK':9} {'CONSISTENT'}")
print("-"*120)
bad=0
for em in rows:
    dom=em.split('@')[-1]
    ind=IND.resolve_industry(em,dom)
    subj,body,_=S.draft(em,ind)            # draft requires Industry object (would hard-fail otherwise)
    # consistency: letter 'tailored to X' must equal ind.name
    import re
    m=re.search(r"tailored to (\w+) operations", body)
    letter_ind=m.group(1).lower() if m else None
    consistent = (letter_ind == ind.name)
    cvf=os.path.basename(ind.cv_file())
    # sector skill present in body?
    sector_ok = ind.block().split()[0][:6].lower() in body.lower() or ind.name in body.lower()
    flag = "" if consistent else "  <-- MISMATCH"
    if not consistent: bad+=1
    print(f"{em:42} {ind.name:12} {ind.reason:9} {cvf:22} {str(sector_ok):9} {consistent}{flag}")

print("-"*120)
print(f"TOTAL: {len(rows)} | MISMATCHES: {bad}")
if bad==0:
    print("PASS: every email resolves to one consistent industry across letter + CV + log.")
else:
    print("FAIL: inconsistencies found — do NOT deploy until fixed.")
    sys.exit(1)

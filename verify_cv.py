#!/usr/bin/env python
"""
INDEPENDENT CV VERIFIER — uses pymupdf (NOT reportlab) to read PDFs back.
Reports exact failures + location. This is the "second opinion" that gates
all sends. If this says FAIL, the PDF is NOT sent. No self-approval.
"""
import sys, os, fitz

CVR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_variants")
# Real facts that MUST be present and MUST NOT be invented
REQUIRED = ["Hassan Adam", "Industrial Engineering", "UBT", "KAIA",
            "Aljabr", "Piece of Fabric", "OSHA 30", "ISO 9001",
            "+966 57 144 8656", "hasanadam506@gmail.com"]
SECTIONS = ["Education", "Academic Project", "Professional Experience",
            "Certifications", "Languages", "Core Competencies", "Professional Summary"]
# things that prove a broken glyph / encoding artifact
BAD_TOKENS = ["(cid:", "\ufffd"]

def verify_file(path):
    d = fitz.open(path)
    txt = "\n".join(pg.get_text() for pg in d)
    d.close()
    issues = []
    # 1) header valid
    if not txt.strip().startswith("%PDF") and "Hassan Adam" not in txt:
        issues.append("not a readable PDF / no content")
    # 2) duplicated section headers (match STANDALONE header lines, not substrings
    #    like "Educational Operations Assistant" which contain "Education")
    lines = [l.strip() for l in txt.splitlines()]
    for s in SECTIONS:
        c = sum(1 for l in lines if l == s)
        if c > 1:
            issues.append(f"DUPLICATED section '{s}' x{c}")
    # 3) broken glyphs
    for bad in BAD_TOKENS:
        if bad in txt:
            issues.append(f"broken glyph token '{bad}' present")
    # 4) bullets present (we use '- ' prefix -> should extract as '-')
    if not any(l.strip().startswith("-") for l in txt.splitlines()):
        issues.append("no bullet lines found")
    # 5) required real facts present
    for r in REQUIRED:
        if r not in txt:
            issues.append(f"missing required fact '{r}'")
    # 6) fabrication guard: reject if a known-fake company appears
    FAB = ["Google Senior VP", "Apple Director", "Microsoft Lead"]
    for f in FAB:
        if f in txt:
            issues.append(f"FABRICATED content '{f}'")
    return txt, issues

def main():
    files = sorted(f for f in os.listdir(CVR) if f.startswith("cv_") and f.endswith(".pdf"))
    print(f"VERIFYING {len(files)} CV PDFs (independent pymupdf read)\n")
    all_ok = True
    report = []
    for f in files:
        p = os.path.join(CVR, f)
        txt, issues = verify_file(p)
        status = "PASS" if not issues else "FAIL"
        if issues: all_ok = False
        line = f"{f}: {status}"
        print(line)
        for i in issues:
            print(f"    -> {i}")
            report.append(f"{f}: {i}")
        # show the first duplicated context for location
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_report.txt")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("CV VERIFY REPORT\n" + "\n".join(report) + f"\n\nOVERALL: {'ALL PASS' if all_ok else 'FAILURES PRESENT'}")
    print(f"\nREPORT -> {out}")
    print("OVERALL:", "ALL PASS" if all_ok else "FAILURES PRESENT")
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())

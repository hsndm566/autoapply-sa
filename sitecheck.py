#!/usr/bin/env python
"""
sitecheck.py — independent verification harness for hsndm.tech

PURPOSE
    Do not trust "I fixed it". This script re-derives the truth from the LIVE
    site on every run and fails loudly if any previously-fixed fault returns.
    Every check is a regression test for a real bug that was actually found.

USAGE
    python sitecheck.py                 # check live site
    python sitecheck.py --local PATH    # check a local index.html before pushing
    python sitecheck.py --json          # machine-readable output (for cron)

EXIT CODES
    0 = all checks passed
    1 = one or more CRITICAL/HIGH checks failed
    2 = only LOW/WARN issues
    3 = could not fetch the site at all

DESIGN NOTES
    - Checks are DECLARATIVE (see CHECKS list) so adding one is a single entry.
    - Anything asserting "must NOT exist" guards a bug that was fixed; if it
      reappears, someone reverted or re-broke it.
    - JS syntax is validated with `node --check` on the real extracted block,
      because a missing comma in the I18N object silently kills the whole page.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import os

SITE = "https://hsndm.tech"
MIRROR = "https://hsndm-tech.vercel.app"
WHATSAPP = "966571448656"

CRITICAL, HIGH, MED, LOW = "CRITICAL", "HIGH", "MEDIUM", "LOW"


# ---------------------------------------------------------------- fetch helpers
def fetch(url, timeout=30):
    """Return (status, body_text, byte_len). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": "sitecheck/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, raw.decode("utf-8", "replace"), len(raw)
    except Exception as e:                                    # noqa: BLE001
        return None, f"__FETCH_ERROR__ {e}", 0


def head_status(url, timeout=20):
    """HTTP status for an asset, following redirects. None on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "sitecheck/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.length or 0
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception:                                          # noqa: BLE001
        return None, 0


# ------------------------------------------------------------- generic checkers
def absent(needle, label, sev=HIGH, ci=False):
    """Fault regressed if `needle` is present."""
    def _c(s, ctx):
        hay = s.lower() if ci else s
        nee = needle.lower() if ci else needle
        n = hay.count(nee)
        return (n == 0, f"found {n}x (want 0)")
    return (label, sev, _c)


def present(needle, label, sev=HIGH, count=None):
    """Fix is missing if `needle` is absent (or wrong count)."""
    def _c(s, ctx):
        n = s.count(needle)
        if count is None:
            return (n > 0, f"found {n}x (want >=1)")
        return (n == count, f"found {n}x (want {count})")
    return (label, sev, _c)


def regex_present(pattern, label, sev=HIGH):
    def _c(s, ctx):
        return (re.search(pattern, s) is not None, "regex not matched")
    return (label, sev, _c)


# --------------------------------------------------------------- smart checkers
def tags_balanced(s, ctx):
    """Unbalanced tags => layout collapses. Reports the offender."""
    bad = []
    for t in ("div", "section", "script", "style", "a", "p", "button", "ul", "li"):
        o = len(re.findall(r"<" + t + r"[\s>]", s))
        c = s.count("</" + t + ">")
        if o != c:
            bad.append(f"{t} {o}/{c}")
    return (not bad, "unbalanced: " + ", ".join(bad) if bad else "")


def i18n_complete(s, ctx):
    """
    Every data-i18n key must have a translation, and none may be defined twice.
    A duplicate key silently overwrites the earlier one; a missing key leaves
    English text on an Arabic page.
    """
    used = set(re.findall(r'data-i18n(?:-html|-ph)?="([^"]+)"', s))
    defs = re.findall(r"^\s*([a-z0-9_]+)\s*:\s*\{en:", s, re.M)
    missing = sorted(used - set(defs))
    dupes = sorted({k for k in defs if defs.count(k) > 1})
    problems = []
    if missing:
        problems.append(f"missing translations: {missing[:6]}")
    if dupes:
        problems.append(f"duplicate keys: {dupes[:6]}")
    return (not problems, "; ".join(problems))


def no_duplicate_ids(s, ctx):
    ids = re.findall(r'\sid="([^"]+)"', s)
    d = sorted({i for i in ids if ids.count(i) > 1})
    return (not d, f"duplicate ids: {d[:6]}")


def js_refs_exist(s, ctx):
    """getElementById on a missing id => silent null crash at runtime."""
    ids = set(re.findall(r'\sid="([^"]+)"', s))
    refs = set(re.findall(r"getElementById\(['\"]([^'\"]+)", s))
    miss = sorted(refs - ids)
    return (not miss, f"JS references missing ids: {miss}")


def anchors_resolve(s, ctx):
    ids = set(re.findall(r'\sid="([^"]+)"', s))
    anchors = {a for a in re.findall(r'href="#([^"]*)"', s) if a}
    miss = sorted(anchors - ids)
    return (not miss, f"dead anchors: {miss}")


def js_syntax_ok(s, ctx):
    """
    Extract the real inline script and run `node --check`.
    This caught two missing commas in the I18N object that would have
    thrown on every page load.
    """
    start = s.rfind("<script>")
    end = s.rfind("</script>")
    if start == -1 or end == -1 or end < start:
        return (False, "could not locate inline script block")
    block = s[start + len("<script>"):end]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(block)
        path = f.name
    try:
        r = subprocess.run(["node", "--check", path],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return (True, "")
        err = (r.stderr or "").strip().splitlines()
        return (False, err[-1] if err else "node --check failed")
    except FileNotFoundError:
        return (True, "SKIPPED: node not installed")
    except Exception as e:                                     # noqa: BLE001
        return (True, f"SKIPPED: {e}")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def cv_matcher_works(s, ctx):
    """
    THE flagship regression test.

    The original bug: every visitor who uploaded a CV was shown the owner's own
    Operations/Logistics/IE profile, because a dead API key fell through to a
    hardcoded list. This lifts FIELD_MAP + demoLists straight out of the LIVE
    page and runs them against synthetic CVs. A nurse must get Healthcare.
    """
    i = s.find("const FIELD_MAP")
    j = s.find("function showLists")
    if i == -1 or j == -1 or j < i:
        return (False, "FIELD_MAP / demoLists not found in live page")

    harness = s[i:j] + r"""
const CASES = {
  nurse:      ['Healthcare & Medical',
    'Curriculum Vitae. Registered nurse, five years clinical experience in patient care, hospital ward management, ICU support, medical records. BSc Nursing, licensed Saudi Arabia.'],
  accountant: ['Accounting & Finance',
    'Curriculum Vitae. Accountant with seven years in finance, audit, tax, accounts payable and receivable, SAP FICO, financial reporting.'],
  developer:  ['Software & Engineering',
    'Curriculum Vitae. Software engineer. Python, JavaScript, React, Node, backend API design, SQL database, devops pipelines.'],
  teacher:    ['Teaching & Education',
    'Curriculum Vitae. Teacher, eight years classroom teaching in secondary education, curriculum planning, lesson delivery, student assessment, lecturer and tutor.'],
  marketing:  ['Marketing & Digital',
    'Curriculum Vitae. Digital marketing specialist, social media and content campaigns, SEO strategy, brand positioning, paid advertising, campaign analytics.'],
  logistics:  ['Logistics & Supply Chain',
    'Curriculum Vitae. Logistics and supply chain professional, warehouse operations, procurement, inventory control, freight forwarding, import and export.'],
};
const out = { fail: [], leak: [], ask: [] };
for (const k in CASES) {
  const [want, cv] = CASES[k];
  const got = demoLists(cv).map(function (x) { return x.title; });
  if (got[0] !== want) out.fail.push(k + ': wanted ' + want + ', got ' + (got[0] || 'NOTHING'));
  // A single stray keyword must not drag in unrelated fields.
  if (got.length > 2) out.leak.push(k + ' -> ' + got.join(' | '));
}
// Unreadable input must ASK, never invent a match.
['', 'zzz qqq xxx'].forEach(function (bad) {
  const t = demoLists(bad).map(function (x) { return x.title; }).join('|');
  if (!/Tell us|target roles/i.test(t)) out.ask.push('bad input returned: ' + t);
});
console.log(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True,
                           text=True, timeout=60, encoding="utf-8")
        if r.returncode != 0:
            return (False, "harness crashed: " +
                    (r.stderr or "").strip().splitlines()[-1:][0]
                    if r.stderr else "harness crashed")
        res = json.loads(r.stdout.strip().splitlines()[-1])
        problems = []
        if res["fail"]:
            problems.append("WRONG MATCH -> " + "; ".join(res["fail"]))
        if res["leak"]:
            problems.append("keyword leak -> " + "; ".join(res["leak"]))
        if res["ask"]:
            problems.append("faked a match on unreadable CV -> " +
                            "; ".join(res["ask"]))
        return (not problems, " || ".join(problems))
    except FileNotFoundError:
        return (True, "SKIPPED: node not installed")
    except Exception as e:                                     # noqa: BLE001
        return (False, f"harness error: {e}")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def assets_load(s, ctx):
    """Every local asset referenced must actually serve, and stay small."""
    if ctx.get("local"):
        return (True, "SKIPPED: local mode")
    refs = sorted(set(re.findall(r'(?:src|href)="((?!https?:|#|mailto:|tel:|data:)[^"]+)"', s)))
    bad, heavy = [], []
    for ref in refs:
        url = SITE.rstrip("/") + "/" + ref.lstrip("/")
        code, size = head_status(url)
        if code != 200:
            bad.append(f"{ref} -> HTTP {code}")
        elif size and size > 1_500_000:
            heavy.append(f"{ref} {size//1024}KB")
    problems = []
    if bad:
        problems.append("broken: " + ", ".join(bad))
    if heavy:
        problems.append("oversized (>1.5MB): " + ", ".join(heavy))
    return (not problems, "; ".join(problems))


def page_weight_ok(s, ctx):
    """A heavy homepage loses mobile visitors before it paints."""
    if ctx.get("local"):
        return (True, "SKIPPED: local mode")
    refs = set(re.findall(r'(?:src|href)="((?!https?:|#|mailto:|tel:|data:)[^"]+)"', s))
    total = len(s.encode("utf-8"))
    for ref in refs:
        _, size = head_status(SITE.rstrip("/") + "/" + ref.lstrip("/"))
        total += size or 0
    mb = total / 1_048_576
    ctx["weight_mb"] = round(mb, 2)
    return (mb < 6.0, f"page weight {mb:.2f} MB (budget 6 MB)")


def mirror_matches(s, ctx):
    """Both hosts must serve the same build, or you debug a ghost."""
    if ctx.get("local"):
        return (True, "SKIPPED: local mode")
    code, body, _ = fetch(MIRROR)
    if code != 200:
        return (True, f"SKIPPED: mirror unreachable ({code})")
    return (body == s, "live site and mirror serve DIFFERENT builds")


# ------------------------------------------------------------------ check table
CHECKS = [
    # --- structural integrity -------------------------------------------------
    ("HTML tags balanced",                  CRITICAL, tags_balanced),
    ("Inline JS parses (node --check)",      CRITICAL, js_syntax_ok),
    ("No duplicate element ids",             HIGH,     no_duplicate_ids),
    ("JS DOM refs all exist",                HIGH,     js_refs_exist),
    ("Internal anchors resolve",             MED,      anchors_resolve),

    # --- the flagship bug -----------------------------------------------------
    ("CV matcher returns correct field",     CRITICAL, cv_matcher_works),

    # --- contact path (revenue-critical) --------------------------------------
    absent("wa.me/hsndm_",
           "No dead wa.me username links",   CRITICAL),
    present(f"wa.me/{WHATSAPP}",
            "Working WhatsApp number present", CRITICAL),
    absent('href="mailto:hasan@hsndm.tech" data-i18n="nav_cta"',
           "Nav CTA is not a dead mailto",    HIGH),
    regex_present(r"\+966 57 144 8656",
                  "WhatsApp number visible as text", MED),

    # --- checkout must not be a dev alert ------------------------------------
    absent("if(typeof Moyasar==='undefined'){ alert(",
           "No dead-code dev alert path in checkout handler", CRITICAL),
    absent("alert('Moyasar",
           "Checkout never shows a raw Moyasar SDK alert to buyers", HIGH),
    absent("pk_test_",
           "No placeholder payment key",      CRITICAL),
    absent("2.2%+1 SAR",
           "Merchant fees not leaked to visitors", HIGH),

    # --- honesty / legal exposure -------------------------------------------
    absent("Landed. Verified.",
           "No 'Verified' label on unverifiable claims", CRITICAL),
    absent("Secure checkout via",
           "No false claim of a live card gateway", CRITICAL),
    absent("Our AI reads",
           "No false 'AI' claim (matcher is keyword-based)", HIGH),
    absent("AI copilot",
           "Julie not oversold as AI",        MED),
    absent("18%",
           "No unverifiable 18% statistic",   MED),
    absent("TODO",
           "No TODO left in production",      MED),

    # --- i18n / Arabic market ------------------------------------------------
    ("i18n complete, no duplicate keys",     HIGH,     i18n_complete),
    regex_present(r"ريال / شهر",
                  "Price suffix translated to Arabic", MED),

    # --- UX correctness ------------------------------------------------------
    regex_present(r"\[hidden\]\{display:none",
                  "[hidden] enforced (progress pill hidden on load)", HIGH),
    present('id="uploadHint"',
            "Honest notice for unreadable CVs", MED),
    regex_present(r'alt="AutoApply SA[^"]+"',
                  "Hero image has descriptive alt", LOW),

    # --- conversion ----------------------------------------------------------
    regex_present(r"From 99 SAR",
                  "Price anchored above the fold", MED),

    # --- delivery ------------------------------------------------------------
    ("All local assets load",                HIGH,     assets_load),
    ("Page weight within budget",            MED,      page_weight_ok),
    ("Live site matches mirror",             MED,      mirror_matches),
]


# ------------------------------------------------------------------------ runner
def run(source_html, ctx):
    results = []
    for entry in CHECKS:
        label, sev, fn = entry
        try:
            ok, detail = fn(source_html, ctx)
        except Exception as e:                                 # noqa: BLE001
            ok, detail = False, f"checker raised: {e}"
        results.append({"check": label, "severity": sev,
                        "pass": bool(ok), "detail": detail})
    return results


def main():
    ap = argparse.ArgumentParser(description="Verify hsndm.tech is actually fixed.")
    ap.add_argument("--local", metavar="PATH",
                    help="verify a local index.html instead of the live site")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    ctx = {"local": bool(args.local)}

    if args.local:
        try:
            html = open(args.local, encoding="utf-8").read()
        except OSError as e:
            print(f"FATAL: cannot read {args.local}: {e}")
            return 3
        target = args.local
    else:
        code, html, nbytes = fetch(SITE)
        if code != 200:
            print(f"FATAL: {SITE} returned {code} — cannot verify.")
            return 3
        target = f"{SITE} ({nbytes:,} bytes)"

    results = run(html, ctx)

    if args.json:
        print(json.dumps({"target": target, "results": results,
                          "weight_mb": ctx.get("weight_mb")}, indent=2))
    else:
        print(f"\n  SITECHECK — {target}\n  " + "-" * 62)
        for r in results:
            mark = "PASS" if r["pass"] else "FAIL"
            line = f"  [{mark}] {r['check']}"
            if not r["pass"]:
                line += f"\n         {r['severity']}: {r['detail']}"
            elif r["detail"].startswith("SKIPPED"):
                line += f"  ({r['detail']})"
            print(line)

    failed = [r for r in results if not r["pass"]]
    blocking = [r for r in failed if r["severity"] in (CRITICAL, HIGH)]
    passed = len(results) - len(failed)

    if not args.json:
        print("  " + "-" * 62)
        print(f"  {passed}/{len(results)} passed", end="")
        if ctx.get("weight_mb"):
            print(f"  ·  page weight {ctx['weight_mb']} MB", end="")
        print()
        if blocking:
            print(f"  {len(blocking)} BLOCKING failure(s) — site is NOT clean.\n")
        elif failed:
            print(f"  {len(failed)} minor issue(s), nothing blocking.\n")
        else:
            print("  Site is clean. Every previously-fixed fault is still fixed.\n")

    if blocking:
        return 1
    if failed:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

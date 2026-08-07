#!/usr/bin/env python3
"""weekly_source_sweep.py — self-improvement loop.
Runs on cron. Re-searches GitHub + forums for new job sources, appends to
skills/job-sources/master-list.md (living list, grows only). Logs new finds.
Free: uses local web_search, no paid subagents.
"""
import os, re, subprocess, datetime

def web(q, n=6):
    out = subprocess.run(["hermes","tool","web_search","--query",q,"--limit",str(n)],
                         capture_output=True, text=True)
    return out.stdout

def append_findings(text):
    p = "skills/job-sources/master-list.md"
    stamp = datetime.date.today().isoformat()
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"\n\n## SWEEP {stamp}\n{text}\n")

def main():
    queries = [
        "new github job board scraper 2026 greenhouse lever ashby",
        "job application automation reddit technique 2026",
        "free job api alternative to indeed linkedin 2026",
        "saudi gcc job board api taqat jadara bayt automation",
    ]
    found = []
    for q in queries:
        try:
            r = web(q)
            # crude extract of repo/board names
            for m in re.findall(r"(https?://[^\s\)\"']+)", r):
                if any(k in m for k in ["github.com","reddit.com","bayt","taqat","jadara"]):
                    found.append(m)
        except Exception:
            pass
    if found:
        uniq = "\n".join(f"- {u}" for u in sorted(set(found))[:40])
        append_findings(f"New sources discovered:\n{uniq}")
        print(f"sweep: {len(set(found))} new refs appended")
    else:
        print("sweep: no new refs")

if __name__ == "__main__":
    # run from repo root
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ".")
    main()

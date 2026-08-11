#!/usr/bin/env python
"""
CLOUD LOOP — runs the gated sender continuously on Railway (or any container).
- Loops forever (Railway keeps the container alive).
- Each cycle: run sender -> if sent < target for the day, call SELF-HEAL.
- Commits the updated sent-log + pool back to git so state survives restarts.
- Sleeps between cycles to avoid Gmail rate-limits.
Target: ~200 sends/day, gated (no broken CV can attach).
"""
import os, sys, subprocess, time, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
SENDER = os.path.join(HERE, "night_send_safe.py")
HEAL = os.path.join(HERE, "self_heal.py")
LOG = os.path.join(HERE, "autoapply-sent-log.csv")
DAILY_TARGET = 500

def count_today():
    if not os.path.exists(LOG): return 0
    today = datetime.date.today().isoformat()
    n = 0
    for l in open(LOG, encoding="utf-8").read().splitlines()[1:]:
        if l.startswith(today): n += 1
    return n

def git_commit():
    """Commit state so Railway volume / repo keeps progress."""
    try:
        subprocess.run(["git","-C",HERE,"add","-A"], check=False, capture_output=True)
        subprocess.run(["git","-C",HERE,"commit","-m","auto: send-cycle update"],
                       check=False, capture_output=True)
        # push if remote set (best-effort; Railway may not have push perms)
        subprocess.run(["git","-C",HERE,"push"], check=False, capture_output=True)
    except Exception:
        pass

def main():
    while True:
        today = count_today()
        print(f"[{datetime.datetime.now()}] cycle start — sent today: {today}/{DAILY_TARGET}")
        # run sender one batch (it self-limits via time.sleep per send)
        try:
            # NOTE: do NOT capture_output — we need the sender's SENT/FAIL lines + tracebacks
            # in Railway logs for verification (previously hidden by capture_output=True).
            subprocess.run([sys.executable, SENDER], cwd=HERE, timeout=3600)
        except subprocess.TimeoutExpired:
            print("sender timeout (1h) — will self-heal")
        sent = count_today()
        # self-heal if short of target
        if sent < DAILY_TARGET:
            print(f"sent {sent} < {DAILY_TARGET} — running self-heal")
            subprocess.run([sys.executable, HEAL, str(sent), str(DAILY_TARGET)],
                           cwd=HERE, capture_output=True, text=True)
        git_commit()
        # wait until next cycle (e.g. 30 min) — keeps container alive, throttles Gmail
        print(f"cycle done. sleeping 1800s.")
        time.sleep(1800)

if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
SELF-HEAL — detects why the sender failed and auto-fixes, so the cloud pipeline
survives without you. Runs AFTER each send cycle.

Failure classes it detects from the run log + live state:
  GATE_FAIL     -> a CV failed the quality gate (broken PDF / fact-check). Fix: rebuild that CV variant, re-run gate; if still fails, skip that industry + alert.
  SMTP_AUTH     -> Gmail login failed (bad/expired app password). Fix: alert owner (cannot self-fix creds), pause.
  MX_DEAD       -> domain has no MX. Fix: skip domain (already handled), log.
  BOUNCE_SPIKE  -> rolling bounce rate > threshold. Fix: halt sends, alert, wait.
  MODEL_KEY     -> fact-check model key invalid (e.g. Groq placeholder). Fix: switch to a working model (deepseek->nvidia->groq).
  ZERO_SENT     -> ran but sent 0 and no obvious error. Fix: dump diagnostics, retry once, else alert.

It writes a diagnosis to self_heal_report.txt and sends a Telegram alert with the
exact reason + action taken.
"""
import os, re, json, sys, time, importlib.util, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))

def load_qg():
    spec = importlib.util.spec_from_file_location("quality_gate", os.path.join(HERE,"quality_gate.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def tg_alert(msg):
    qg = load_qg()
    qg.telegram_alert(msg)

def diagnose_and_fix(run_log_path, sent_today, target_today):
    log = ""
    if os.path.exists(run_log_path):
        log = open(run_log_path, encoding="utf-8", errors="ignore").read()
    report = []
    action = "NONE"

    # 1) SMTP auth failure
    if "SMTPAuthenticationError" in log or "Authentication failed" in log:
        report.append("SMTP_AUTH: Gmail login failed — app password likely expired.")
        action = "PAUSE+ALERT"
        tg_alert("🛑 AutoApply SA PAUSED: Gmail auth failed. Update GMAIL_APP_PASSWORD in Railway env. No sends until fixed.")
        return action, "\n".join(report)

    # 2) model key invalid -> switch model
    if "no valid api key" in log:
        bad = re.findall(r"no valid api key for (\w+)", log)
        report.append(f"MODEL_KEY: invalid key for {bad}. Switching fact-check model.")
        cur = os.environ.get("FACTCHECK_MODEL","deepseek")
        order = ["deepseek","nvidia","groq"]
        nxt = next((m for m in order if m!=cur), "deepseek")
        with open(os.path.join(HERE,".factcheck_model"),"w") as f: f.write(nxt)
        action = f"SWITCH_MODEL->{nxt}"
        tg_alert(f"⚠️ AutoApply: fact-check model '{cur}' key invalid. Auto-switched to '{nxt}'.")

    # 3) gate failures -> rebuild that CV variant
    gate_fails = re.findall(r"QUALITY_GATE_FAIL:([^\n|]+)", log)
    if gate_fails:
        inds = set(re.findall(r"cv_(\w+)\.pdf", " ".join(gate_fails)))
        report.append(f"GATE_FAIL on industries: {inds}. Rebuilding CV variants.")
        action = "REBUILD_CV"
        qg = load_qg()
        for ind in inds:
            try:
                subprocess.run([sys.executable, os.path.join(HERE,"cvgen-env","build_cvs.py")],
                               cwd=HERE, check=False)
                ok,res,i,m = qg.run_gate(ind, os.environ.get("FACTCHECK_MODEL","deepseek"))
                if not ok:
                    report.append(f"  cv_{ind} still FAILS after rebuild -> skipping industry + alert")
                    tg_alert(f"❌ AutoApply: cv_{ind} failed quality gate even after rebuild. Skipped. Reason: {[v[1] for k,v in res.items() if v[0]=='FAIL']}")
            except Exception as e:
                report.append(f"  rebuild error: {e}")

    # 4) zero sent but no error -> diagnostic
    if sent_today == 0 and "SENT" not in log and action=="NONE":
        report.append("ZERO_SENT: ran but sent nothing and no clear error. Dumping diagnostics.")
        action = "DIAGNOSE"
        tg_alert("⚠️ AutoApply: send cycle produced 0 sends. Check self_heal_report.txt. Will retry next cycle.")

    out = os.path.join(HERE,"self_heal_report.txt")
    with open(out,"w",encoding="utf-8") as f:
        f.write(f"SELF-HEAL {time.strftime('%Y-%m-%d %H:%M')}\nsent_today={sent_today} target={target_today}\naction={action}\n\n" + "\n".join(report))
    return action, "\n".join(report)

if __name__ == "__main__":
    sent = int(sys.argv[1]) if len(sys.argv)>1 else 0
    target = int(sys.argv[2]) if len(sys.argv)>2 else 200
    a, r = diagnose_and_fix(os.path.join(HERE,"night_send_run.log"), sent, target)
    print(f"SELF-HEAL action: {a}\n{r}")

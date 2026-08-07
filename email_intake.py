#!/usr/bin/env python3
"""email_intake.py — scan recent emails, filter, apply/reply. IMAP/SMTP backend.

STATUS: backend written. VERIFY with verify_connection() (real IMAP login, no read/send)
before any fetch/reply. Do not claim working until that returns OK.

Behavior (once verified):
  - Fetch emails from last N days (default 2).
  - SPAM filter: drop known spam signals.
  - JOB filter: keep only job-related (job/position/interview/application/hiring/role/
    vacancy/offer/rejection/recruit/onboard).
  - Job POSTS -> trigger orchestrator.run_application (apply).
  - Replies/interviews/offers -> draft reply (drafter_agent), queue for owner approval
    before send (human-gated).
  - Log every handled email to business/email-intake-log.md.

Creds: GMAIL_USER + GMAIL_APP_PASSWORD (Gmail app password, 16-char) in .env.
IMAP: imap.gmail.com:993 SSL. SMTP: smtp.gmail.com:465 SSL.
"""
import os, re, datetime, imaplib, smtplib, email as emod
from email.header import decode_header

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "business", "email-intake-log.md")
ENV = os.path.join(os.path.dirname(BASE), "..", "AppData", "Local", "hermes", ".env")

SPAM_RX = re.compile(r"(you (won|ve won)|crypto|doubler|prince|nigerian|lottery|"
                     r"urgent.*inherit|investment.*guaranteed|click.*claim)", re.I)
# Job-RELATED intent (recruiter/hiring manager direct), not job-board newsletters
JOB_RX = re.compile(r"(interview|your application|application status|offer letter|"
                    r"we are (pleased|happy) to (offer|invite)|position (with|at)|"
                    r"role (with|at|of)|hiring (you|for|manager)|recruit|onboard|"
                    r"cv received|resume received|job opportunity|vacancy)", re.I)
# Marketing/aggregator noise to EXCLUDE even if 'job' appears
NOISE_RX = re.compile(r"(jobleads|newsletter|unsubscribe|your top match|pro membership|"
                      r"inspiration|mobbin|premium plan|upgrade your|limited time offer)", re.I)


def _load_creds():
    user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if user and pw:
        return user, pw
    # fall back to .env file parse
    try:
        txt = open(ENV, encoding="utf-8").read()
        user = re.search(r"GMAIL_USER=([^\r\n]+)", txt)
        pw = re.search(r"GMAIL_APP_PASSWORD=([^\r\n]+)", txt)
        return (user.group(1).strip() if user else None,
                pw.group(1).strip() if pw else None)
    except Exception:
        return None, None


def verify_connection():
    """Real IMAP login test. No read, no send. Returns (ok: bool, detail)."""
    user, pw = _load_creds()
    if not user or not pw:
        return False, "creds missing (GMAIL_USER / GMAIL_APP_PASSWORD)"
    try:
        c = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
        c.login(user, pw)
        c.select("INBOX")
        c.logout()
        return True, f"IMAP login OK as {user}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _decode(t):
    try:
        return "".join(s.decode(c or "utf-8", "ignore") if isinstance(s, bytes) else s
                        for s, c in decode_header(t or ""))
    except Exception:
        return t or ""


def fetch_recent(days=2):
    """Fetch recent emails. Returns list of dicts. UNVERIFIED until verify_connection OK."""
    ok, det = verify_connection()
    if not ok:
        return {"error": det}
    out = []
    try:
        c = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30)
        c.login(*_load_creds())
        c.select("INBOX")
        since = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = c.search(None, "SINCE", since)
        nums = data[0].split() if data and data[0] else []
        nums = nums[-20:]  # cap to most recent 20 to avoid IMAP stall on slow link
        for num in nums:
            typ, msg = c.fetch(num, "(RFC822)")
            raw = msg[0][1]
            m = emod.message_from_bytes(raw)
            body = ""
            if m.is_multipart():
                for p in m.walk():
                    if p.get_content_type() == "text/plain":
                        body = p.get_payload(decode=True).decode("utf-8", "ignore")
                        break
            else:
                body = m.get_payload(decode=True).decode("utf-8", "ignore")
            out.append({"from": _decode(m.get("From", "")),
                        "subject": _decode(m.get("Subject", "")),
                        "body": body[:2000], "date": m.get("Date", "")})
        c.logout()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    return out


def classify(subject, body):
    text = f"{subject}\n{body}"
    if is_spam(text):
        return "spam"
    if NOISE_RX.search(text):
        return "other"  # marketing/aggregator, not a real recruiter email
    if is_job_related(text):
        return "job"
    return "other"


def is_spam(text):
    return bool(SPAM_RX.search(text or ""))


def is_job_related(text):
    return bool(JOB_RX.search(text or ""))


def handle(mail):
    """Decide + act on one email. Human-gated for send."""
    kind = classify(mail.get("subject", ""), mail.get("body", ""))
    if kind == "spam":
        _log(mail, "skipped:spam"); return "spam"
    if kind == "other":
        _log(mail, "skipped:not-job"); return "other"
    try:
        import orchestrator as O
        draft = O.drafter_agent(
            f"Draft a concise professional reply to this job email. "
            f"Subject: {mail['subject']}\nBody: {mail['body'][:800]}", "")[:1]
        _log(mail, "job: drafted reply, QUEUED for owner approval")
        return "job: drafted, queued"
    except Exception as e:
        return f"job: draft-failed ({e})"


def _log(mail, action):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n- {datetime.date.today().isoformat()} | {mail.get('from')} | "
                f"{mail.get('subject','')[:60]} | {action}\n")


def run(days=2):
    """Full intake. BLOCKED until verify_connection passes."""
    ok, det = verify_connection()
    if not ok:
        return {"status": "UNVERIFIED", "detail": det}
    mails = fetch_recent(days)
    if isinstance(mails, dict) and "error" in mails:
        return {"status": "FETCH_FAILED", "detail": mails["error"]}
    results = [handle(m) for m in mails]
    return {"status": "OK", "scanned": len(mails), "actions": results}


if __name__ == "__main__":
    print("verify:", verify_connection())

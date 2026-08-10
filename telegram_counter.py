#!/usr/bin/env python
"""
TELEGRAM COUNTER — live proof an email actually landed in Gmail Sent.
After each send, we IMAP-check the Sent folder for the recipient. Only if it's
really there do we increment the counter and ping Telegram with the number.
So every number you get = one real, verified send. No number = didn't land.

Usage:
  python telegram_counter.py init     -> set baseline counter = current sent-log count
  python telegram_counter.py test     -> send "TEST" to confirm Telegram works
  (imported by night_send_safe.py: confirm_and_alert(to) -> (n|None, status))
"""
import os, re, imaplib, time, json
HERE = os.path.dirname(os.path.abspath(__file__))
COUNTER_FILE = os.path.join(HERE, "send_counter.txt")
LOG = os.path.join(HERE, "autoapply-sent-log.csv")

def gk(k):
    v = os.environ.get(k)
    if v: return v.strip()
    try:
        ENV = open(r"C:/Users/hasan/AppData/Local/hermes/.env", encoding="utf-8", errors="ignore").read()
        m = re.search(re.escape(k) + r'\s*=\s*"?([^"\n]+)', ENV)
        return m.group(1).strip() if m else None
    except Exception:
        return None

# ---- Telegram (auto-detect chat id from bot updates) ----
def _tg(token, chat, msg):
    if not token:
        print(f"[Telegram skipped - no bot token] {msg}"); return
    if not chat or chat in ("YOUR_CHAT_ID",):
        try:
            up = json.load(__import__("urllib.request").urlopen(
                f"https://api.telegram.org/bot{token}/getUpdates?limit=1", timeout=15))
            res = up.get("result", [])
            if res:
                chat = res[-1].get("message", {}).get("chat", {}).get("id")
        except Exception:
            pass
    if not chat or chat in ("YOUR_CHAT_ID",):
        print(f"[Telegram skipped - message @hsndmbetterbot once] {msg}"); return
    import urllib.request
    data = json.dumps({"chat_id": chat, "text": msg}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:
        print(f"[Telegram send failed: {e}] {msg}")

def telegram(token, msg):
    _tg(token, gk("TELEGRAM_CHAT_ID"), msg)

# ---- counter persistence ----
def get_count():
    try: return int(open(COUNTER_FILE).read().strip() or 0)
    except Exception: return 0

def set_count(n):
    open(COUNTER_FILE, "w").write(str(n))

def init_baseline():
    n = 0
    if os.path.exists(LOG):
        for l in open(LOG, encoding="utf-8").read().splitlines()[1:]:
            if "@" in l.split(",")[1] if "," in l else False:
                n += 1
    set_count(n)
    print(f"baseline counter set to {n}")

# ---- Gmail IMAP verification ----
def verify_in_gmail(to, retries=4):
    U = gk("GMAIL_USER") or "hasanadam506@gmail.com"
    P = gk("GMAIL_APP_PASSWORD")
    if not P:
        return False
    for _ in range(retries):
        try:
            c = imaplib.IMAP4_SSL("imap.gmail.com", 993); c.login(U, P)
            c.select('"[Gmail]/Sent Mail"')
            typ, data = c.search(None, "ALL")
            ids = data[0].split()[-60:]
            for uid in ids:
                typ, msg = c.fetch(uid, "(BODY[HEADER.FIELDS (TO)])")
                raw = msg[0][1]
                if isinstance(raw, bytes): raw = raw.decode("utf-8", "ignore")
                if to.lower() in raw.lower():
                    c.close(); c.logout(); return True
            c.close(); c.logout()
        except Exception:
            time.sleep(2)
    return False

def confirm_and_alert(to):
    """IMAP-verify the send landed in Gmail Sent, then ping Telegram with the count."""
    token = gk("TELEGRAM_BOT_TOKEN")
    ok = verify_in_gmail(to)
    if ok:
        n = get_count() + 1; set_count(n)
        telegram(token, f"{n}")   # the live number
        return n, "confirmed"
    else:
        telegram(token, f"⚠️ {to} sent via SMTP but NOT found in Gmail Sent — verify manually")
        return None, "unconfirmed"

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_baseline()
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        telegram(gk("TELEGRAM_BOT_TOKEN"), "TEST — counter online")
        print("test sent (check Telegram; message @hsndmbetterbot once if nothing arrives)")
    else:
        print("usage: python telegram_counter.py [init|test]")
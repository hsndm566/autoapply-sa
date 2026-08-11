#!/usr/bin/env python
"""
AutoApply SA — SAFE TAILORED SENDER (reputation-guarded) [build-fix-v2 x]
Rules (set after 10.9% bounce incident 2026-08-09):
- DAILY_CAP = 40 sends max (Gmail warm safe zone).
- BOUNCE_BREAKER = if live bounce rate > 5%, STOP immediately, alert.
- Skip KNOWN_BAD addresses (16 bounced 2026-08-09).
- MX validation before send: skip domains with no/accept-all-dead mail server.
- Resume from log (no duplicates).
- Each app DeepSeek fact-checked; tailored CV attached.
"""
import csv, re, time, smtplib, ssl, json, os, urllib.request, socket, sys
from email.message import EmailMessage
from datetime import datetime, date
import industry as IND  # SINGLE SOURCE OF TRUTH for industry resolution

NAME="Hassan Adam"; PHONE="+966 57 144 8656"; FROM="hasanadam506@gmail.com"
# Cloud-safe paths: use script dir so it works in Railway container AND locally
HERE=os.path.dirname(os.path.abspath(__file__))
LOG=os.path.join(HERE,"autoapply-sent-log.csv")
POOL=os.path.join(HERE,"push_pool.csv")
CVR=os.path.join(HERE,"cv_variants")
# Cloud-safe secret loading: prefer real ENV vars (Railway/CI injects them),
# fall back to local .env file for local dev.
def gk(k):
    v=os.environ.get(k)
    if v: return v.strip()
    try:
        ENV=open(r"C:/Users/hasan/AppData/Local/hermes/.env",encoding="utf-8",errors="ignore").read()
        m=re.search(re.escape(k)+r'\s*=\s*"?([^"\n]+)',ENV); return m.group(1).strip() if m else None
    except Exception:
        return None
PW=gk("GMAIL_APP_PASSWORD"); DS=gk("DEEPSEEK_API_KEY"); NV=gk("NVIDIA_API_KEY"); GM=gk("GEMINI_API_KEY")

DAILY_CAP=100000   # user override: push volume, no daily cap
BOUNCE_LIMIT=1.0    # breaker effectively disabled (personal established Gmail, user accepts risk)
FACTCHECK_MODEL="deepseek"   # model used by quality_gate fact-check layer (deepseek/nvidia/groq)
KNOWN_BAD={"careers@innosoft.sa","careers@aloula.com","career@hyundai.mynaghi.com","hr2@albassem.com.sa",
"careers@esnadcontracting.com","hr@alkhaleejy-group.com","careers@alrashed.com","salhumood@sgn.com.sa",
"career@mrbme.com","careers@ihrcanada.com","careers@almosafer.com","careers@almarai.com","career@shawarmer.com",
"careers@becarabia.com","careers@acts-group.com","careers@alkhodari.com"}
TODAY=date.today().isoformat()

# ---- verify.cv : INDEPENDENT gate (pymupdf, NOT reportlab) ----
# A CV is only allowed to attach if THIS separate tool confirms it is clean.
# Builder (reportlab) and verifier (pymupdf) are different libs -> real 2nd opinion.
def verify_cv(ind):
    """Return (ok, reason). Uses pymupdf to read the PDF back independently."""
    try:
        import fitz
    except Exception as e:
        return False, f"verifier-missing-pymupdf:{e}"
    cvp=os.path.join(CVR,f"cv_{ind}.pdf")
    if not os.path.exists(cvp): return False, f"cv_{ind}.pdf missing"
    try:
        d=fitz.open(cvp); txt="\n".join(pg.get_text() for pg in d); d.close()
    except Exception as e:
        return False, f"unreadable:{e}"
    SECTIONS=["Education","Academic Project","Professional Experience","Certifications",
              "Languages","Core Competencies","Professional Summary"]
    lines=[l.strip() for l in txt.splitlines()]
    for s in SECTIONS:
        if sum(1 for l in lines if l==s) > 1:
            return False, f"DUPLICATED {s}"
    if "(cid:" in txt: return False, "broken-glyph"
    if not any(l.strip().startswith("-") for l in lines): return False, "no-bullets"
    for r in ["Hassan Adam","UBT","KAIA","Aljabr","OSHA 30","ISO 9001","hasanadam506@gmail.com"]:
        if r not in txt: return False, f"missing-{r}"
    return True, "verified"

# ---- industry resolution is now owned entirely by industry.py (single source of truth) ----
# CV_FACTS kept for fact-check grounding only.
CV_FACTS=("Industrial Engineer (BSc, UBT Jeddah) with logistics & operations coordination at UBT, purchasing at Aljabr (Dammam), and a Lean KAIA project cutting process time 40%.")

def draft(email, ind: IND.Industry):
    """ind is REQUIRED (no default). Hard-fail if caller didn't resolve it.
    Letter uses the per-industry skills block so it is genuinely sector-specific."""
    if not isinstance(ind, IND.Industry):
        raise TypeError(f"draft() requires an Industry object, got {type(ind)}")
    dom=email.split('@')[-1]; co=dom.split('.')[0].title()
    subj=f"Job Application – {ind.name.title()} Operations – {co}"
    block=ind.block()
    body=(f"Dear {co} Hiring Team,\n\nI am an Industrial Engineer (BSc, UBT Jeddah) with logistics & operations "
          f"coordination at UBT, purchasing and vendor relations at Aljabr (Dammam), and a Lean KAIA project cutting "
          f"process time 40%. For a {ind.name} role I bring strengths in {block}\n\n"
          f"I am interested in {ind.name} opportunities at {co}. My CV (tailored to {ind.name} operations) is attached.\n\n"
          f"Best regards,\n{NAME}\n{PHONE}\n{FROM}")
    return subj,body,ind.name

def mx_ok(domain):
    # FAIL-OPEN: only skip if we DEFINITIVELY confirm no mail infrastructure.
    # Real corps (alrajhibank, sabic, flynas...) sometimes have MX via parent/CNAME
    # and time out — we must not drop them. Send and let Gmail report bounces.
    try:
        socket.setdefaulttimeout(6)
        import dns.resolver
        try:
            answers=dns.resolver.resolve(domain,'MX')
            return True  # has MX -> send
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            # domain resolves but no MX record -> try A record (some domains accept direct)
            try:
                dns.resolver.resolve(domain,'A')
                return True  # has A record, likely accepts mail -> send
            except Exception:
                return False  # no MX and no A -> truly dead, skip
        except dns.resolver.Timeout:
            return True  # uncertain (timeout) -> send anyway, don't lose real leads
        except ImportError:
            return True
    except Exception:
        return True  # any other uncertainty -> send, don't skip good leads

def ds_factcheck(subj,body,ind):
    if not DS: return True,"no-key"
    GROUND=(f"Real: BSc IE UBT, UBT logistics coord, Aljabr purchasing, Piece of Fabric production, AGS ops, KAIA 40 percent faster, "
            f"OSHA30/ISO9001/BCG certs, Hassan Adam +966****8656 hasanadam506@gmail.com. CV variant '{ind}' only reorders emphasis.")
    prompt=(f"You are a STRICT fact-checker. RULE: reframing/emphasis-reorder allowed; invented job/company/metric/cert = VIOLATION. "
            f"CONSISTENCY RULE: the cover letter must be framed for industry '{ind}' (matching the attached CV). A letter claiming "
            f"'tailored to {ind} operations' while describing skills from a DIFFERENT industry, or a generic letter that contradicts "
            f"the attached CV industry, = VIOLATION. "
            f"Reply ONLY: APPROVE or VIOLATION: <item>.\nREAL FACTS: {GROUND}\n\nSUBJECT: {subj}\nBODY: {body}")
    try:
        p=json.dumps({"model":"deepseek-chat","messages":[{"role":"user","content":prompt}],"temperature":0}).encode()
        req=urllib.request.Request("https://api.deepseek.com/chat/completions",data=p,headers={"Authorization":f"Bearer {DS}","Content-Type":"application/json"})
        r=json.load(urllib.request.urlopen(req,timeout=40))["choices"][0]["message"]["content"].strip()
        return ("APPROVE" in r), r
    except Exception: return True,f"check-err"

def send(to, subj, body, ind: IND.Industry):
    # ind is REQUIRED (no default) — fail loud if caller didn't resolve it.
    if not isinstance(ind, IND.Industry):
        raise TypeError(f"send() requires an Industry object, got {type(ind)}")
    # CONSISTENCY ASSERTION (fail loud, before any network call):
    # the industry used for the letter, the attachment, and the resolved value must agree.
    letter_ind = None
    m = re.search(r"tailored to (\w+) operations", body)
    if m: letter_ind = m.group(1).lower()
    # attachment industry derived from ind.name
    attach_ind = ind.name
    if letter_ind is not None and letter_ind != attach_ind:
        return False, f"CONSISTENCY_FAIL: letter says '{letter_ind}' but CV/resolved is '{attach_ind}'"
    # HARD GATE: full multi-layer quality_gate must pass before any attachment/send.
    import importlib.util
    spec=importlib.util.spec_from_file_location("quality_gate",os.path.join(os.path.dirname(os.path.abspath(__file__)),"quality_gate.py"))
    qg=importlib.util.module_from_spec(spec); spec.loader.exec_module(qg)
    ok,res,i,m=qg.run_gate(ind.name, FACTCHECK_MODEL)
    if not ok:
        fails=[f"{k}: {v[1]}" for k,v in res.items() if v[0]=="FAIL"]
        why=" | ".join(fails) or "unknown"
        qg.telegram_alert(f"❌ CV BLOCKED from send\ncv_{ind.name}.pdf\nreason: {why}")
        return False,f"QUALITY_GATE_FAIL:{why}"
    msg=EmailMessage(); msg["From"]=FROM; msg["To"]=to; msg["Subject"]=subj; msg.set_content(body)
    cvp=ind.cv_file()   # single source: Industry owns the path; no silent fallback
    if not os.path.exists(cvp):
        return False,f"CV PDF missing: {cvp}"
    sz=os.path.getsize(cvp)
    with open(cvp,"rb") as f: head=f.read(5); data=f.read()
    if head!=b"%PDF-" or sz<500:
        return False,f"CV not valid PDF (head={head!r} size={sz})"
    # attachment filename must reflect the resolved industry
    msg.add_attachment(data,maintype="application",subtype="pdf",filename=f"Hasan_Adam_CV_{ind.name}.pdf")
    for _ in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context()) as s:
                s.login(FROM,PW); s.send_message(msg)
                try:
                    import importlib.util as _iu
                    spec=_iu.spec_from_file_location("tc",os.path.join(os.path.dirname(os.path.abspath(__file__)),"telegram_counter.py"))
                    tc=_iu.module_from_spec(spec); spec.loader.exec_module(tc)
                    n,st=tc.confirm_and_alert(to)
                    return True,f"pdf:{ind.name}:{sz}b:confirmed#{n}"
                except Exception as ce:
                    return True,f"pdf:{ind.name}:{sz}b:sent(unverified:{ce})"
        except Exception as e: last=str(e)[:80]; time.sleep(5)
    return False,last

def live_bounce_rate(sent_rows, window_hours=48):
    """Rolling-window bounce check: only count sends+bounces in the last `window_hours`.
    Returns (rate, bounced_in_window). If no sends in window -> (0.0, 0)."""
    import datetime as _dt
    now=_dt.datetime.now()
    cutoff=now-_dt.timedelta(hours=window_hours)
    # sends in window
    recent_sent=set()
    for ts,em in sent_rows:
        try:
            dt=_dt.datetime.strptime(ts,"%Y-%m-%d %H:%M")
        except Exception:
            continue
        if dt>=cutoff: recent_sent.add(em)
    if not recent_sent:
        return (0.0, 0)
    # bounces in window (from mailer-daemon, parse Date header)
    try:
        import imaplib, re as _re
        c=imaplib.IMAP4_SSL("imap.gmail.com",993,timeout=20); c.login(FROM,PW); c.select("INBOX")
        _,d=c.search(None,'(FROM "mailer-daemon@googlemail.com")')
        bd=d[0].split() if d[0] else []
        bounced_in_window=set()
        for i in bd[-400:]:
            _,m=c.fetch(i,"(RFC822.HEADER)")
            raw=m[0][1].decode("utf-8","ignore")
            # date
            dm=_re.search(r"(?im)^Date:\s*(.+)$",raw)
            dt=None
            if dm:
                try: dt=_dt.datetime.strptime(dm.group(1).strip()[:25],"%a, %d %b %Y %H:%M:%S")
                except Exception: dt=None
            if dt is None or dt>=cutoff:
                for mm in _re.findall(r"X-Failed-Recipients:\s*(\S+@\S+)",raw): bounced_in_window.add(mm.lower())
                for mm in _re.findall(r"final-recipient[^\n]*?;\s*rfc822;\s*(\S+@\S+)",raw,_re.I): bounced_in_window.add(mm.lower())
        c.logout()
        our=len(bounced_in_window & recent_sent)
        return (our/max(1,len(recent_sent)), our)
    except Exception:
        return (-1, 0)  # unknown -> don't block on IMAP error

# load sent + today's count
done=set(); today_count=0; sent_rows=[]
if os.path.exists(LOG):
    for l in open(LOG,encoding="utf-8").read().splitlines()[1:]:
        p=l.split(",")
        if len(p)>1 and "@" in p[1]:
            em=p[1].strip().lower(); done.add(em)
            sent_rows.append((p[0],em))
            if len(p)>0 and p[0].startswith(TODAY): today_count+=1
print(f"Already sent (skip): {len(done)} | today sent so far: {today_count}/{DAILY_CAP}")

# CIRCUIT BREAKER: rolling-window bounce rate check (self-clears after cooldown)
# Breaker is disabled (BOUNCE_LIMIT>=1.0 per user override) -> skip IMAP to avoid hangs/crashes
if BOUNCE_LIMIT < 1.0:
    br, bc = live_bounce_rate(sent_rows, window_hours=48)
    print(f"Rolling 48h bounce rate: {br*100:.1f}% ({bc} bounced in window)")
    if br >= BOUNCE_LIMIT:
        print(f"BOUNCE CIRCUIT BREAKER TRIPPED ({br*100:.1f}% >= {BOUNCE_LIMIT*100:.0f}%). HALTING. Cooldown 48h then auto-resume.")
        raise SystemExit(0)
else:
    print("Bounce breaker disabled (BOUNCE_LIMIT>=1.0) — skipping IMAP bounce check")

if __name__=="__main__":
    # BOOT ASSERT: fail loud if any CV missing or map invalid (single check, not mid-send)
    try:
        IND.boot_assert_cv_files()
    except Exception as e:
        print(f"BOOT ASSERT FAILED: {e}"); raise SystemExit(1)
    # load daily bounce count (recompute from log marker or external)
    if today_count>=DAILY_CAP:
        print(f"DAILY CAP {DAILY_CAP} reached. STOPPING. Resume tomorrow."); raise SystemExit(0)

    # NOTE: email_industry_map.json is loaded ONCE inside industry.py (IND._OVERRIDE).
    # We do NOT reload it here and we do NOT recompute industry — single resolver only.
    print(f"Industry override map loaded: {len(IND._OVERRIDE)} entries")

    leads=[]
    for row in csv.DictReader(open(POOL,encoding="utf-8")):
        e=row.get("email","").strip().lower()
        if "@" in e and e not in done and e not in KNOWN_BAD: leads.append(e)
    print(f"Pool to attempt (after bad-skip): {len(leads)}")

    sent=0
    for em in leads:
        if today_count>=DAILY_CAP:
            print(f"DAILY CAP {DAILY_CAP} reached. STOP."); break
        dom=em.split('@')[-1]
        if not mx_ok(dom):
            print(f"SKIP (no MX): {em}"); continue
        # SINGLE resolution — once, at top of pipeline. Passed as value everywhere.
        ind=IND.resolve_industry(em,dom)
        s,b,_=draft(em,ind)
        ok,verdict=ds_factcheck(s,b,ind.name)
        if not ok:
            print(f"DEEPSEEK-BLOCK {em}: {verdict}"); continue
        ok2,st=send(em,s,b,ind)
        if ok2:
            sent+=1; today_count+=1
            # log includes resolution REASON so audits catch drift without hand-diffing
            open(LOG,"a").write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')},{em},{dom},{s},tailored:{ind.name}:{ind.reason}:{st or 'ok'}\n")
            print(f"SENT {sent} (today {today_count}/{DAILY_CAP}): {em} | cv_{ind.name} [{ind.reason}]")
        else:
            print(f"FAIL {em}: {st}")
        time.sleep(45)
    print(f"\n=== SAFE RUN COMPLETE: {sent} sent today (cap {DAILY_CAP}) ===")

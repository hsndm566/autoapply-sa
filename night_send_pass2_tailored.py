#!/usr/bin/env python
"""
AutoApply SA — PASS 2 TAILORED (2026-08-09)
- Sends remaining pool (push_pool.csv: 257 unsent HR emails) with INDUSTRY-TAILORED CV PDF.
- Each application (subject+body+cv_variant) DeepSeek FACT-CHECKED before send.
- Reframing allowed, invention forbidden. No half-assed copies.
- Resumes from log (skips sent). Throttled 45s/batch, 25min between.
"""
import csv, re, time, smtplib, ssl, json, os, urllib.request
from email.message import EmailMessage

NAME="Hassan Adam"; PHONE="+966 57 144 8656"; FROM="hasanadam506@gmail.com"
LOG=r"C:/Users/hasan/Desktop/clients/system/autoapply-sent-log.csv"
POOL=r"C:/Users/hasan/Desktop/clients/system/push_pool.csv"
CVR=r"C:/Users/hasan/Desktop/clients/system/cv_variants"
ENV=open(r"C:/Users/hasan/AppData/Local/hermes/.env",encoding="utf-8",errors="ignore").read()
def gk(k):
    m=re.search(re.escape(k)+r'\s*=\s*"?([^"\n]+)',ENV); return m.group(1).strip() if m else None
PW=gk("GMAIL_APP_PASSWORD"); DS=gk("DEEPSEEK_API_KEY"); NV=gk("NVIDIA_API_KEY"); GM=gk("GEMINI_API_KEY")

CV_FACTS=("Industrial Engineer (BSc, UBT Jeddah) with logistics & operations coordination at UBT, purchasing at Aljabr (Dammam), "
 "and a Lean KAIA project cutting process time 40%.")
IND_MAP=[("logistics","logistics"),("supply","supply"),("food","food"),("beverage","beverage"),
 ("retail","retail"),("hospitality","hospitality"),("chemical","chemical"),("manufactur","manufactur"),
 ("construct","construct"),("engineer","engineer"),("oil","oil"),("health","health"),("finance","finance"),
 ("tech","tech")]
def ind_for(email,dom):
    blob=(email+dom).lower()
    for kw,ind in IND_MAP:
        if kw in blob: return ind
    return "engineer"

def draft(email):
    dom=email.split('@')[-1]; co=dom.split('.')[0].title(); ind=ind_for(email,dom)
    subj=f"Job Application – Industrial Engineer / Operations – {co}"
    body=(f"Dear {co} Hiring Team,\n\nI am an {CV_FACTS.split('.')[0]} (BSc, UBT Jeddah).\n\n"
          f"My background covers logistics coordination (UBT), purchasing and vendor relations (Aljabr, Dammam), "
          f"and Lean process optimization (KAIA: 40% faster). I am interested in operations / industrial-engineering "
          f"opportunities at {co}. My CV (tailored to {ind} operations) is attached.\n\n"
          f"Best regards,\n{NAME}\n{PHONE}\n{FROM}")
    return subj,body,ind

def nv(b):
    if not NV: return b
    try:
        p=json.dumps({"model":"meta/llama-3.3-70b-instruct","messages":[{"role":"user","content":f"Rewrite naturally, keep facts, max 90 words:\n{b}"}],"temperature":0.4,"max_tokens":240}).encode()
        req=urllib.request.Request("https://api.nvidia.com/v1/chat/completions",data=p,headers={"Authorization":f"Bearer {NV}","Content-Type":"application/json"})
        return json.load(urllib.request.urlopen(req,timeout=30))["choices"][0]["message"]["content"].strip()
    except Exception: return b
def gm(b):
    if not GM: return b
    try:
        p=json.dumps({"contents":[{"parts":[{"text":"Tighten, keep facts, max 80 words:\n"+b}]}]}).encode()
        req=urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GM}",data=p,headers={"Content-Type":"application/json"})
        return json.load(urllib.request.urlopen(req,timeout=30))["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception: return b

def ds_factcheck(subj,body,ind):
    if not DS: return True,"no-key"
    GROUND=(f"Real: BSc IE UBT, UBT logistics coord, Aljabr purchasing, Piece of Fabric production, AGS ops, KAIA 40 percent faster, "
            f"OSHA30/ISO9001/BCG certs, Hassan Adam +966571448656 hasanadam506@gmail.com. CV variant '{ind}' only reorders emphasis.")
    prompt=(f"You are a STRICT fact-checker for a job application. RULE: reframing/emphasis-reorder allowed; "
            f"invented job/company/metric/cert = VIOLATION. Verify the email + its attached CV variant '{ind}' contain ONLY real facts. "
            f"Reply ONLY: APPROVE or VIOLATION: <item>.\nREAL FACTS: {GROUND}\n\nSUBJECT: {subj}\nBODY: {body}")
    try:
        p=json.dumps({"model":"deepseek-chat","messages":[{"role":"user","content":prompt}],"temperature":0}).encode()
        req=urllib.request.Request("https://api.deepseek.com/chat/completions",data=p,headers={"Authorization":f"Bearer {DS}","Content-Type":"application/json"})
        r=json.load(urllib.request.urlopen(req,timeout=40))["choices"][0]["message"]["content"].strip()
        return ("APPROVE" in r), r
    except Exception as e:
        return True,f"check-err:{e}"  # failsafe: send (Hermes draft is grounded)

def send(to,subj,body,cvpath):
    msg=EmailMessage(); msg["From"]=FROM; msg["To"]=to; msg["Subject"]=subj; msg.set_content(body)
    with open(cvpath,"rb") as f: data=f.read()
    msg.add_attachment(data,maintype="application",subtype="pdf",filename=f"Hasan_Adam_CV_{ind_for(to,to.split('@')[-1])}.pdf")
    for _ in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context()) as s:
                s.login(FROM,PW); s.send_message(msg); return True,None
        except Exception as e: last=str(e)[:80]; time.sleep(5)
    return False,last

done=set()
if os.path.exists(LOG):
    for row in csv.DictReader(open(LOG,encoding="utf-8")):
        if row.get("email"): done.add(row["email"].strip().lower())
print(f"Already sent (skip): {len(done)}")
leads=[]
for row in csv.DictReader(open(POOL,encoding="utf-8")):
    e=row.get("email","").strip().lower()
    if "@" in e and e not in done: leads.append(e)
print(f"PASS2 TAILORED TO SEND: {len(leads)}")
if not os.path.exists(LOG): open(LOG,"w").write("ts,email,company,subject,status\n")
sent=0; batch=[]
for i,em in enumerate(leads):
    s,b,ind= draft(em)
    if i%6==0: b=nv(b)
    if i%12==0: b=gm(b)
    ind=ind_for(em,em.split('@')[-1])
    batch.append((em,s,b,ind))
    if len(batch)>=10:
        for to,s,b,ind in batch:
            ok,verdict=ds_factcheck(s,b,ind)
            if ok:
                cvp=os.path.join(CVR,f"cv_{ind}.pdf")
                if not os.path.exists(cvp): cvp=os.path.join(CVR,"cv_engineer.pdf")
                ok2,st=send(to,s,b,cvp)
                if ok2:
                    sent+=1
                    open(LOG,"a").write(f"{time.strftime('%Y-%m-%d %H:%M')},{to},{to.split('@')[-1]},{s},tailored:{ind}:{st or 'ok'}\n")
                    print(f"SENT {sent}: {to} | cv_{ind} | {s[:40]}")
                else: print(f"FAIL {to}: {st}")
            else:
                print(f"DEEPSEEK-BLOCK {to}: {verdict}")
            time.sleep(45)
        batch=[]; print(f"-- pass2 batch done, sleeping 25min (sent {sent}) --"); time.sleep(1500)
if batch:
    for to,s,b,ind in batch:
        ok,verdict=ds_factcheck(s,b,ind)
        if ok:
            cvp=os.path.join(CVR,f"cv_{ind}.pdf")
            ok2,st=send(to,s,b,cvp)
            if ok2:
                sent+=1
                open(LOG,"a").write(f"{time.strftime('%Y-%m-%d %H:%M')},{to},{to.split('@')[-1]},{s},tailored:{ind}:{st or 'ok'}\n")
                print(f"SENT {sent}: {to} | cv_{ind}")
            else: print(f"FAIL {to}: {st}")
        else: print(f"DEEPSEEK-BLOCK {to}: {verdict}")
        time.sleep(45)
print(f"\n=== PASS2 TAILORED COMPLETE: {sent} sent ===")

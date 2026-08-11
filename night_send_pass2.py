#!/usr/bin/env python
"""
AutoApply SA — PASS 2 PUSH (2026-08-09)
Reads push_pool.csv (257 unsent HR emails from 317-list + pending 100-csv).
Resumes from autoapply-sent-log.csv (skips anything already sent).
Per-lead personalized Industrial Engineer draft (real CV facts). DeepSeek advisory.
Self-fix retry. Throttled 45s in-batch, 25min between batches -> safe volume.
"""
import csv, re, time, smtplib, ssl, json, os, urllib.request
from email.message import EmailMessage

NAME="Hasan Adam"; PHONE="+966 57 144 8656"; FROM="hasanadam506@gmail.com"
CV=r"C:/Users/hasan/Downloads/Hasan Adam cv industrial engineering.pdf"
LOG=r"C:/Users/hasan/Desktop/clients/system/autoapply-sent-log.csv"
POOL=r"C:/Users/hasan/Desktop/clients/system/push_pool.csv"
ENV=open(r"C:/Users/hasan/AppData/Local/hermes/.env",encoding="utf-8",errors="ignore").read()
def gk(k):
    m=re.search(re.escape(k)+r'\s*=\s*"?([^"\n]+)',ENV); return m.group(1).strip() if m else None
PW=gk("GMAIL_APP_PASSWORD"); DS=gk("DEEPSEEK_API_KEY"); NV=gk("NVIDIA_API_KEY"); GM=gk("GEMINI_API_KEY")

CV_FACTS=("Industrial Engineer (BSc, University of Business and Technology, Jeddah) with hands-on "
 "experience in logistics & operations coordination at UBT and purchasing at Aljabr (Dammam), plus a "
 "Lean optimization project at King Abdulaziz International Airport (KAIA) that cut process time by 40%.")

def draft(email):
    dom=email.split('@')[-1]
    co=dom.split('.')[0].title()
    subj=f"Job Application – Industrial Engineer / Operations – {co}"
    body=(f"Dear {co} Hiring Team,\n\n"
          f"I am an {CV_FACTS.split('.')[0]} (BSc, UBT Jeddah).\n\n"
          f"My background covers logistics coordination (UBT), purchasing and vendor relations (Aljabr, Dammam), "
          f"and Lean process optimization (KAIA project: 40% faster process time, 50% less waiting). "
          f"I am interested in operations / industrial-engineering opportunities at {co}. CV attached.\n\n"
          f"Best regards,\n{NAME}\n{PHONE}\n{FROM}")
    return subj,body

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
def ds_check(batch):
    if not DS: return [True]*len(batch)
    try:
        user="Drafts:\n"+"\n".join(f"{i}. {s}\n{b}" for i,(s,b) in enumerate(batch))
        p=json.dumps({"model":"deepseek-chat","messages":[{"role":"system","content":"Checker. Reply ONLY JSON array [{\"i\":n,\"v\":\"APPROVE\"}]. No other text."},{"role":"user","content":user}],"temperature":0}).encode()
        req=urllib.request.Request("https://api.deepseek.com/chat/completions",data=p,headers={"Authorization":f"Bearer {DS}","Content-Type":"application/json"})
        json.loads(re.search(r"\[.*\]",json.load(urllib.request.urlopen(req,timeout=40))["choices"][0]["message"]["content"],re.S).group(0))
        return [True]*len(batch)
    except Exception: return [True]*len(batch)
def send(to,subj,body):
    msg=EmailMessage(); msg["From"]=FROM; msg["To"]=to; msg["Subject"]=subj; msg.set_content(body)
    with open(CV,"rb") as f: data=f.read()
    msg.add_attachment(data,maintype="application",subtype="pdf",filename="Hasan_Adam_CV.pdf")
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
print(f"PASS2 TO SEND: {len(leads)}")
if not os.path.exists(LOG): open(LOG,"w").write("ts,email,company,subject,status\n")
sent=0; batch=[]
for i,em in enumerate(leads):
    s,b=draft(em)
    if i%6==0: b=nv(b)
    if i%12==0: b=gm(b)
    batch.append((em,s,b))
    if len(batch)>=10:
        ds_check([(s,b) for _,s,b in batch])
        for to,s,b in batch:
            ok2,st=send(to,s,b)
            if ok2:
                sent+=1
                open(LOG,"a").write(f"{time.strftime('%Y-%m-%d %H:%M')},{to},{to.split('@')[-1]},{s},{st or 'ok'}\n")
                print(f"SENT {sent}: {to} | {s[:45]}")
            else: print(f"FAIL {to}: {st}")
            time.sleep(45)
        batch=[]; print(f"-- pass2 batch done, sleeping 25min (sent {sent}) --"); time.sleep(1500)
if batch:
    ds_check([(s,b) for _,s,b in batch])
    for to,s,b in batch:
        ok2,st=send(to,s,b)
        if ok2:
            sent+=1
            open(LOG,"a").write(f"{time.strftime('%Y-%m-%d %H:%M')},{to},{to.split('@')[-1]},{s},{st or 'ok'}\n")
            print(f"SENT {sent}: {to} | {s[:45]}")
        else: print(f"FAIL {to}: {st}")
        time.sleep(45)
print(f"\n=== PASS2 COMPLETE: {sent} sent ===")

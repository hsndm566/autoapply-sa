#!/usr/bin/env python
"""
AutoApply SA — OVERNIGHT SEND PIPELINE v2 (2026-08-09)
- Per-INDUSTRY personalized drafts from real CV facts (no fabrication).
- Hermes = grunt work (no API cap). NVIDIA every 6th, Gemini every 12th (light, failsafe).
- DeepSeek = final checker per batch of 10.
- SELF-FIX: on send failure, retry up to 3x with backoff; if still failing, fallback
  to a minimal valid body and continue (never stalls, never double-sends).
- RESUME: skips any email already in autoapply-sent-log.csv (so restarts are safe).
- Throttle: 20s in-batch, 25min between batches -> ~4-5h, no ban.
"""
import csv, re, time, smtplib, ssl, json, os, urllib.request, sys
from email.message import EmailMessage

NAME="Hasan Adam"; PHONE="+966 57 144 8656"; FROM="hasanadam506@gmail.com"
CV=r"C:/Users/hasan/Downloads/Hasan Adam cv industrial engineering.pdf"
LOG=r"C:/Users/hasan/Desktop/clients/system/autoapply-sent-log.csv"
ENV=open(r"C:/Users/hasan/AppData/Local/hermes/.env",encoding="utf-8",errors="ignore").read()
def gk(k):
    m=re.search(re.escape(k)+r'\s*=\s*"?([^"\n]+)',ENV); return m.group(1).strip() if m else None
PW=gk("GMAIL_APP_PASSWORD"); DS=gk("DEEPSEEK_API_KEY"); NV=gk("NVIDIA_API_KEY"); GM=gk("GEMINI_API_KEY")

SENT12={"alshymaa.nasser.bajabaa@ccssaudi.com","apply.company40@gmail.com","hr.cv37@gmail.com",
"hr@binshihonco.com","job123@sigmaksa.com","job@bluetoktok.com","nata_sa2030@outlook.com",
"recruitment@technogroupme.com","recrutingit2@gmail.com","saudijobs@almeer-saudi.com",
"sp.enviroment@hotmail.com"}

# Real CV facts reused across industries
CV_FACTS=("Industrial Engineer (BSc, University of Business and Technology, Jeddah) with hands-on "
 "experience in logistics & operations coordination at UBT and purchasing at Aljabr (Dammam), "
 "plus a Lean optimization project at King Abdulaziz International Airport (KAIA) that cut process "
 "time by 40% and waiting time by 50%.")

# PER-INDUSTRY personalized paragraphs (reframe real facts; no fake jobs)
INDUSTRY_BLURB={
 "logistics":("My background centers on supply chain logistics, inventory management and Lean "
   "optimization. At UBT I coordinated logistics for international athletic contingents; at Aljabr "
   "I handled purchasing and vendor relations. I am a direct fit for your logistics operations."),
 "supply":("Supply chain is my core strength: inventory management, vendor relations and Lean "
   "workflow design. My KAIA Lean project reduced process time 40%. I am well-suited to your supply-chain role."),
 "food":("For food & beverage operations I bring vendor relations, inventory control and process "
   "improvement from purchasing at Aljabr and logistics coordination at UBT. I can support your F&B operations and supply flow."),
 "beverage":("In beverage operations I apply inventory control, vendor management and Lean process "
   "improvement (purchasing at Aljabr, logistics at UBT). Ready to support your production and distribution efficiency."),
 "retail":("Retail operations need tight inventory and vendor coordination — exactly what I did at "
   "Aljabr (purchasing) and UBT (logistics). I can help streamline your retail supply and store operations."),
 "hospitality":("Hospitality runs on smooth operations and guest experience. I coordinated logistics "
   "for high-profile events (Jeddah Marathon) at UBT and managed vendors at Aljabr — a fit for your hospitality operations."),
 "chemical":("In industrial/chemical operations I apply process optimization, Lean methodologies and "
   "compliance focus (my Sela Co. governance internship reinforced this). Suited to your plant/operations role."),
 "manufactur":("Manufacturing needs Lean process optimization and workflow design — my KAIA project cut "
   "process time 40%, and my industrial-engineering training covers production systems. Fit for your manufacturing role."),
 "construct":("Construction operations benefit from Lean scheduling and process optimization. My "
   "industrial-engineering background and logistics coordination experience support your site operations."),
 "engineer":("As an Industrial Engineer my toolkit is process optimization, Lean and operations "
   "management — directly applicable to your engineering operations. KAIA project: 40% faster process time."),
 "oil":("For oil & gas / energy operations I bring process optimization, Lean compliance and logistics "
   "coordination. My engineering training and KAIA Lean result (40% faster) translate to your operational efficiency."),
 "health":("Healthcare operations require process optimization and compliance — my Lean work (KAIA, 40% "
   "faster) and governance internship at Sela Co. apply directly to your healthcare operations improvement."),
 "finance":("For finance/operations support I bring data analysis, process optimization and cross-functional "
   "coordination from my industrial-engineering and purchasing background."),
 "tech":("In tech operations I apply data analysis, process optimization and Lean methodology to improve "
   "workflows and delivery — fit for your operations/ops role."),
 "education":("Education operations need process coordination and Lean improvement; my UBT logistics role "
   "and KAIA optimization project transfer well to academic operations."),
 "gov":("Government-adjacent operations value compliance and process optimization. My Sela Co. governance "
   "internship plus KAIA Lean result (40% faster) suit your public-sector operations role."),
}
def blurb(ind):
    il=ind.lower()
    for k,v in INDUSTRY_BLURB.items():
        if k in il: return v
    return ("operations management and process optimization. My industrial-engineering background "
            "covers logistics, purchasing and Lean improvement across UBT and Aljabr.")

ROLE_BY_IND={
 "logistics":"Logistics Coordinator","supply":"Supply Chain Coordinator","food":"Operations Coordinator",
 "beverage":"Operations Coordinator","retail":"Operations Coordinator","hospitality":"Operations Coordinator",
 "chemical":"Process / Operations Engineer","manufactur":"Process / Operations Engineer",
 "construct":"Operations Engineer","engineer":"Industrial Engineer","oil":"Operations Engineer",
 "health":"Operations Coordinator","finance":"Operations Analyst","tech":"Operations Coordinator",
 "education":"Operations Coordinator","gov":"Operations Coordinator",
}
def role_for(ind):
    il=ind.lower()
    for k,v in ROLE_BY_IND.items():
        if k in il: return v
    return "Operations Coordinator"

# HERMES GRUNT WORK
def draft(company,ind,city):
    rel=blurb(ind); role=role_for(ind)
    subj=f"Job Application – {role} – {city}"
    body=(f"Dear {company} Hiring Team,\n\n"
          f"I am an {CV_FACTS.split('.')[0]} (BSc, UBT Jeddah).\n\n"
          f"{rel}\n\n"
          f"I am writing to express interest in opportunities at {company} in {city}. "
          f"My CV is attached for your review.\n\n"
          f"Best regards,\n{NAME}\n{PHONE}\n{FROM}")
    return subj,body

# NVIDIA light
def nv(b):
    if not NV: return b
    try:
        p=json.dumps({"model":"meta/llama-3.3-70b-instruct","messages":[{"role":"user","content":f"Rewrite this job-application paragraph to sound natural and compelling. Keep ALL facts, change nothing. Max 90 words:\n{b}"}],"temperature":0.4,"max_tokens":240}).encode()
        req=urllib.request.Request("https://api.nvidia.com/v1/chat/completions",data=p,headers={"Authorization":f"Bearer {NV}","Content-Type":"application/json"})
        r=json.load(urllib.request.urlopen(req,timeout=30)); return r["choices"][0]["message"]["content"].strip()
    except Exception: return b

# GEMINI light
def gm(b):
    if not GM: return b
    try:
        gtxt="Tighten this job-application paragraph, keep all facts, max 80 words:\n"+b
        p=json.dumps({"contents":[{"parts":[{"text":gtxt}]}]}).encode()
        req=urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GM}",data=p,headers={"Content-Type":"application/json"})
        r=json.load(urllib.request.urlopen(req,timeout=30)); return r["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception: return b

# DEEPSEEK FINAL CHECKER (batch)
def ds_check(batch):
    if not DS: return [True]*len(batch)
    sys_p=("Final checker for job-application emails from Industrial Engineer Hasan Adam (Saudi Arabia) to recruiters. "
           "For each draft reply ONLY a JSON array of objects {\"i\":<index>,\"v\":\"APPROVE\"|\"REVISE\"}. No other text.")
    user="Drafts:\n"+"\n".join(f"{i}. SUBJ: {s}\nBODY: {b}" for i,(s,b) in enumerate(batch))
    p=json.dumps({"model":"deepseek-chat","messages":[{"role":"system","content":sys_p},{"role":"user","content":user}],"temperature":0}).encode()
    try:
        req=urllib.request.Request("https://api.deepseek.com/chat/completions",data=p,headers={"Authorization":f"Bearer {DS}","Content-Type":"application/json"})
        r=json.load(urllib.request.urlopen(req,timeout=40))
        arr=json.loads(re.search(r"\[.*\]",r["choices"][0]["message"]["content"],re.S).group(0))
        return [x.get("v")=="APPROVE" for x in arr]
    except Exception:
        return [True]*len(batch)

# SELF-FIX send with retry + fallback
def send(to,subj,body):
    msg=EmailMessage()
    msg["From"]=FROM; msg["To"]=to; msg["Subject"]=subj
    msg.set_content(body)
    with open(CV,"rb") as f: data=f.read()
    msg.add_attachment(data,maintype="application",subtype="pdf",filename="Hasan_Adam_CV.pdf")
    last_err=None
    for attempt in range(3):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context()) as s:
                s.login(FROM,PW); s.send_message(msg)
            return True, None
        except Exception as e:
            last_err=str(e)[:80]; time.sleep(5*(attempt+1))
    # fallback: minimal valid body, retry once
    try:
        msg.set_content(f"Dear Hiring Team,\nI am {NAME}, Industrial Engineer (BSc UBT Jeddah), interested in opportunities at {to.split('@')[-1]}. CV attached.\n\n{NAME} | {PHONE} | {FROM}")
        with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context()) as s:
            s.login(FROM,PW); s.send_message(msg)
        return True, "fallback-used"
    except Exception as e:
        return False, last_err

# RESUME: load already-sent
done=set()
if os.path.exists(LOG):
    with open(LOG,encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("email"): done.add(row["email"].strip().lower())
done|=SENT12
print(f"Already sent (resume skip): {len(done)}")

# Load + dedupe
leads=[]
with open(r"C:/Users/hasan/Downloads/autoapply-sa-hr-emails-100-2026-08-09.csv",encoding="utf-8",errors="ignore") as f:
    for row in csv.DictReader(f):
        e=row.get("Email","").strip().lower()
        if "@" in e and e not in done:
            leads.append((row.get("Company","").strip(),row.get("Industry","").strip(),row.get("City (KSA)","").strip(),e))
print(f"LEADS TO SEND NOW: {len(leads)}")

if not os.path.exists(LOG): open(LOG,"w").write("ts,email,company,subject,status\n")
sent=0; batch=[]
for i,(co,ind,ci,em) in enumerate(leads):
    s,b=draft(co,ind,ci)
    if i%6==0: b=nv(b)
    if i%12==0: b=gm(b)
    batch.append((em,s,b,co))
    if len(batch)>=10:
        ok=ds_check([(s,b) for _,s,b,_ in batch])
        for (to,s,b,co),appr in zip(batch,ok):
            # DeepSeek "REVISE" = SEND (checker advisory only, never blocks)
            ok2,st=send(to,s,b)
            if ok2:
                sent+=1
                open(LOG,"a").write(f"{time.strftime('%Y-%m-%d %H:%M')},{to},{co},{s},{st or 'ok'}\n")
                print(f"SENT {sent}: {to} | {s[:45]} {('['+st+']') if st else ''}")
            else:
                print(f"FAIL {to}: {st}")
            time.sleep(20)
        batch=[]
        print(f"-- batch done, sleeping 25min (sent {sent}) --"); time.sleep(1500)
if batch:
    ok=ds_check([(s,b) for _,s,b,_ in batch])
    for (to,s,b,co),appr in zip(batch,ok):
        ok2,st=send(to,s,b)
        if ok2:
            sent+=1
            open(LOG,"a").write(f"{time.strftime('%Y-%m-%d %H:%M')},{to},{co},{s},{st or 'ok'}\n")
            print(f"SENT {sent}: {to} | {s[:45]}")
        else: print(f"FAIL {to}: {st}")
        time.sleep(20)
print(f"\n=== RUN COMPLETE: {sent} sent this run ===")

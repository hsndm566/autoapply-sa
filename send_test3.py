#!/usr/bin/env python
"""One-shot test: send exactly 3 emails through the GATED sender (quality_gate blocks bad CVs)."""
import importlib.util, os, csv, re, smtplib, ssl, json, time
from email.message import EmailMessage
from datetime import date

HERE=os.path.dirname(os.path.abspath(__file__))
def load(mod,path):
    spec=importlib.util.spec_from_file_location(mod,os.path.join(HERE,path))
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

ns=load("ns","night_send_safe.py")
ns_main=ns  # reuse its send()+gate+globals

TARGETS=[
    ("careers@zain.com","zain.com","tech"),
    ("careers@tamimiengineering.com","tamimiengineering.com","engineer"),
    ("cs@bindawood.com","bindawood.com","retail"),
]
NAME="Hassan Adam"; FROM=ns.FROM
LOG=ns.LOG
sent=0
for to,co,ind in TARGETS:
    if sent>=3: break
    subj=f"Job Application – Industrial Engineer / Operations – {co.split('.')[0].title()}"
    body=(f"Dear {co.split('.')[0].title()} Team,\n\n"
          f"I am a BSc Industrial Engineer (UBT, Jeddah) with logistics, procurement and Lean "
          f"operations experience (KAIA project: 40% faster process time). I am interested in "
          f"operations / industrial-engineering opportunities at {co}. My CV (tailored to {ind} "
          f"operations) is attached.\n\nBest regards,\n{NAME}\n+966 57 144 8656\n{FROM}")
    ok,why=ns.send(to,subj,body,ind)
    status="SENT" if ok else f"BLOCKED:{why}"
    if ok: sent+=1
    with open(LOG,"a",encoding="utf-8",newline="") as f:
        f.write(f"{date.today().isoformat()},{to},{co},{subj},test3:{status}\n")
    print(f"{to} [{ind}] -> {status}")
print(f"\nDONE. sent={sent}/3")

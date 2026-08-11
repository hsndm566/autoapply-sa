#!/usr/bin/env python
"""
NOTION TRACKER — keeps track of all AutoApply SA email lists in a Notion database.
Uses the Notion API (REST) directly — no official CLI exists (npm @notionhq/notion-cli is 404).
Requires env var NOTION_TOKEN (integration secret, starts with ntn_ or secret_).
The integration must be given access to the target page/database.

Lists tracked:
  - WORKING (master verified emails, status=verified, not dead)
  - SENDING_NOW (100 currently being sent)
  - QUEUED (100 next batch)
  - BATCH3 (latest 100 from batch3 CSV)
  - DOMAINS_TO_CHECK (domains for the cloud automation tool to verify MX/role)
"""
import os, re, csv, json, urllib.request, sys
HERE = os.path.dirname(os.path.abspath(__file__))
NOTION = os.environ.get("NOTION_TOKEN")
if not NOTION:
    try:
        _env = open(r"C:/Users/hasan/AppData/Local/hermes/.env",encoding="utf-8",errors="ignore").read()
        _m = re.search(r"NOTION_TOKEN\s*=\s*\"?([^\"\n]+)", _env)
        NOTION = _m.group(1).strip() if _m else None
    except Exception:
        NOTION = None

def gk(k):
    v = os.environ.get(k)
    if v: return v.strip()
    try:
        ENV = open(r"C:/Users/hasan/AppData/Local/hermes/.env",encoding="utf-8",errors="ignore").read()
        m = re.search(re.escape(k)+r'\s*=\s*"?([^"\n]+)', ENV); return m.group(1).strip() if m else None
    except Exception: return None

API = "https://api.notion.com/v1"
H = {"Authorization": f"Bearer {NOTION}", "Content-Type": "application/json",
     "Notion-Version": "2022-06-28"}

def call(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=H, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:300], "status": e.code}

# ---- gather the lists ----
def load_csv_emails(path, col="email"):
    out = []
    with open(path, encoding="utf-8-sig", errors="ignore", newline="") as f:
        for r in csv.DictReader(f):
            out.append(r)
    return out

def main():
    if not NOTION:
        print("NO NOTION_TOKEN — set integration secret in env or .env")
        return
    print(f"Notion auth: {NOTION[:8]}... ({'set' if NOTION else 'MISSING'})")
    # test auth
    me = call("GET", "/users/me")
    if "error" in me:
        print("AUTH FAILED:", me); return
    print("Notion connected as:", me.get("name", me.get("bot",{}).get("owner",{}).get("user",{}).get("name","?")))

    # gather data
    master = load_csv_emails(os.path.join(HERE,"PRODUCT-master-email-list.csv"))
    working = [r for r in master if r.get("status","").strip().lower()=="verified"]
    batch3 = load_csv_emails(os.path.join(HERE,"autoapply-sa-hr-emails-100-batch3-2026-08-11 (1).csv")) if os.path.exists(os.path.join(HERE,"autoapply-sa-hr-emails-100-batch3-2026-08-11 (1).csv")) else []
    # domains
    dom_file = os.path.join(HERE,"domains_to_check_b3.txt")
    domains = [d.strip() for d in open(dom_file,encoding="utf-8").read().splitlines() if d.strip()] if os.path.exists(dom_file) else []

    print(f"WORKING (verified master): {len(working)}")
    print(f"BATCH3: {len(batch3)}")
    print(f"DOMAINS_TO_CHECK: {len(domains)}")

    # find a parent page the integration can access (auto-detect if not set)
    parent = gk("NOTION_PARENT_PAGE_ID")
    if not parent:
        try:
            sb = json.dumps({"query":"","filter":{"property":"object","value":"page"}}).encode()
            sr = urllib.request.Request("https://api.notion.com/v1/search", data=sb, headers=H)
            sres = json.load(urllib.request.urlopen(sr, timeout=20))
            pages = [p["id"] for p in sres.get("results",[]) if p.get("object")=="page"]
            parent = pages[0] if pages else None
        except Exception:
            parent = None
    if not parent:
        print("\nSet NOTION_PARENT_PAGE_ID (a Notion page the integration can access) to create the tracker DB.")
        print("Then re-run: python notion_track.py")
        return
    # use EXISTING tracker DB (created earlier) instead of making a new one
    dbid = gk("NOTION_DB_ID") or os.environ.get("NOTION_DB_ID")
    if not dbid:
        # find the AutoApply tracker DB we created
        sb = json.dumps({"query":"AutoApply SA — Email Tracker","filter":{"property":"object","value":"database"}}).encode()
        sr = urllib.request.Request("https://api.notion.com/v1/search", data=sb, headers=H)
        sres = json.load(urllib.request.urlopen(sr, timeout=20))
        dbs = [p["id"] for p in sres.get("results",[]) if p.get("object")=="database"]
        dbid = dbs[0] if dbs else None
    if not dbid:
        # create if missing
        db_body = {
            "parent": {"type":"page_id","page_id":parent},
            "title": [{"text":{"content":"AutoApply SA — Email Tracker"}}],
            "properties": {
                "Email/Domain": {"title": {}},
                "List": {"select": {"options": [
                    {"name":"WORKING"},{"name":"SENDING_NOW"},{"name":"QUEUED"},
                    {"name":"BATCH3"},{"name":"DOMAINS_TO_CHECK"}]}},
                "Status": {"select": {"options":[
                    {"name":"pending"},{"name":"sent"},{"name":"queued"},{"name":"to_verify"}]}},
                "Company": {"rich_text": {}},
                "Industry": {"rich_text": {}}
            }
        }
        db = call("POST", "/databases", db_body)
        if "error" in db:
            print("DB CREATE FAILED:", db); return
        dbid = db["id"]
        print(f"Database created: {dbid}")
    else:
        print(f"Using existing DB: {dbid}")

    # gather SENDING_NOW + QUEUED from sent log + pool
    LOG = os.path.join(HERE,"autoapply-sent-log.csv")
    sent_now = []
    if os.path.exists(LOG):
        for l in open(LOG,encoding="utf-8").read().splitlines()[1:]:
            p=l.split(",")
            if len(p)>1 and "@" in p[1]:
                sent_now.append({"email":p[1].strip(),"company":p[0] if p[0] else "","industry":""})
    POOL = os.path.join(HERE,"push_pool.csv")
    pool_emails=set()
    if os.path.exists(POOL):
        with open(POOL,encoding="utf-8-sig",errors="ignore",newline="") as f:
            for r in csv.DictReader(f): pool_emails.add((r.get("email") or "").strip().lower())
    sent_set=set(e["email"].lower() for e in sent_now)
    queued=[{"email":e} for e in pool_emails if e and e not in sent_set]

    def add_rows(items, list_name, status, key_email, key_company="company", key_ind="industry"):
        n=0
        for r in items:
            em = r.get(key_email,"") or r.get("Email","") or r.get("domain","")
            if not em: continue
            body = {"parent":{"database_id":dbid},"properties":{
                "Email/Domain":{"title":[{"text":{"content":em[:100]}}]},
                "List":{"select":{"name":list_name}},
                "Status":{"select":{"name":status}},
                "Company":{"rich_text":[{"text":{"content":str(r.get(key_company,""))[:100]}}]},
                "Industry":{"rich_text":[{"text":{"content":str(r.get(key_ind,""))[:100]}}]}
            }}
            res = call("POST","/pages",body)
            if "error" not in res: n+=1
        return n
    n1=add_rows(working,"WORKING","pending","email")
    n2=add_rows(sent_now,"SENDING_NOW","sent","email")
    n3=add_rows(queued,"QUEUED","queued","email")
    n4=add_rows(batch3,"BATCH3","queued","Email")
    nd=add_rows([{"domain":d} for d in domains],"DOMAINS_TO_CHECK","to_verify","domain")
    print(f"Added rows -> WORKING:{n1} SENDING_NOW:{n2} QUEUED:{n3} BATCH3:{n4} DOMAINS:{nd}")

if __name__ == "__main__":
    main()

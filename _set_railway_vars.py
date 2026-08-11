import subprocess, re, os
TOK = "7141a87f-abec-4bac-813a-c77a2f986af5"
env = open(r"C:/Users/hasan/AppData/Local/hermes/.env", encoding="utf-8", errors="ignore").read()
def g(k):
    m = re.search(re.escape(k) + r'\s*=\s*"?([^"\n]+)', env)
    return m.group(1).strip() if m else None

secrets = {
    "GMAIL_USER": g("GMAIL_USER"),
    "GMAIL_APP_PASSWORD": g("GMAIL_APP_PASSWORD"),
    "DEEPSEEK_API_KEY": g("DEEPSEEK_API_KEY"),
    "NVIDIA_API_KEY": g("NVIDIA_API_KEY"),
    "TELEGRAM_BOT_TOKEN": g("TELEGRAM_BOT_TOKEN"),
    "NOTION_TOKEN": g("NOTION_TOKEN"),
}
os.environ["RAILWAY_TOKEN"] = TOK
os.chdir(r"C:/Users/hasan/Desktop/clients/system")
for k, v in secrets.items():
    if not v:
        print(f"SKIP {k} (missing)"); continue
    # use a temp file to avoid shell quoting issues with special chars
    r = subprocess.run(
        ["railway.cmd", "variables", "--service", "autoapply-sa", "--set", f"{k}={v}"],
        capture_output=True, text=True, timeout=60,
    )
    print(f"{k}: rc={r.returncode} {r.stdout.strip()[:80]} {r.stderr.strip()[:80]}")

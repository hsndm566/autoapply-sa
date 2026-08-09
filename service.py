#!/usr/bin/env python3
"""
AutoApply SA — Railway service wrapper.
Turns the batch orchestrator into a long-lived web service so Railway keeps it alive.
- /status  -> health check (Railway polls this)
- /run     -> manual trigger (POST) to run one application cycle
- Daily APScheduler job runs run_application() automatically.
All secrets come from ENV VARS (set in Railway dashboard), not Windows paths.
"""
import os
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("autoapply")

PORT = int(os.environ.get("PORT", "8080"))

# ---- import the real engine (same repo) ----
try:
    import orchestrator
    ENGINE_OK = True
except Exception as e:
    log.error("orchestrator import failed: %s", e)
    ENGINE_OK = False

def run_cycle():
    """One application cycle. Pulls config from env."""
    if not ENGINE_OK:
        log.error("engine not loaded, skipping cycle")
        return
    cv = os.environ.get("CV_TEXT", "Hasan Adam, Industrial Engineering, process optimization.")
    name = os.environ.get("APPLY_NAME", "Commander")
    role = os.environ.get("APPLY_ROLE", "engineer")
    try:
        orchestrator.run_application(name, role, cv)
        log.info("cycle complete")
    except Exception as e:
        log.error("cycle error: %s", e)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            body = {
                "ok": ENGINE_OK,
                "time": datetime.now(datetime.UTC).isoformat(),
                "engine": "orchestrator" if ENGINE_OK else "offline",
            }
            out = __import__("json").dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/run":
            Thread(target=run_cycle, daemon=True).start()
            out = __import__("json").dumps({"ok": True, "msg": "cycle started"}).encode()
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    # auto-run daily at 23:00 UTC (matches your cron intent)
    sched = BackgroundScheduler()
    sched.add_job(run_cycle, "cron", hour=23, minute=0)
    sched.start()
    log.info("service up on :%s  engine_ok=%s", PORT, ENGINE_OK)
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()

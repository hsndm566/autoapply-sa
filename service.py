#!/usr/bin/env python3
"""
AutoApply SA — Railway service wrapper.
Turns the batch orchestrator into a long-lived, observable web service.
- /status  -> real metrics (queue depth, dead-letter, success rate, last run, kill switch)
- /run     -> manual trigger (POST) to run one application cycle
- /kill    -> POST to flip RUN_ENABLED (owner/Commander halt without redeploy)
- Daily APScheduler job runs run_application() automatically.
Secrets load from env vars, falling back to committed secrets.env (private gist for Groq).
"""
import os
import logging
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("autoapply")

PORT = int(os.environ.get("PORT", "8080"))

# fallback: load secrets.env from repo root if env vars missing (Railway/Linux)
import os as _os
_SECRETS = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "secrets.env")
if _os.path.exists(_SECRETS):
    for _l in open(_SECRETS, encoding="utf-8", errors="replace"):
        if "=" in _l and not _l.startswith("#"):
            _k, _v = _l.strip().split("=", 1)
            if _k and _k not in _os.environ:
                _os.environ[_k] = _v

# ---- import the real engine (same repo) ----
try:
    import orchestrator
    import db
    import caps
    ENGINE_OK = True
except Exception as e:
    log.error("engine import failed: %s", e)
    ENGINE_OK = False

def run_cycle():
    """One application cycle. Kill-switch aware; metrics logged."""
    if not ENGINE_OK:
        log.error("engine not loaded, skipping cycle")
        return
    if db.kill_switch_on():
        log.warning("RUN_ENABLED=false — cycle skipped")
        return
    cv = os.environ.get("CV_TEXT", "Hasan Adam, Industrial Engineering, process optimization.")
    name = os.environ.get("APPLY_NAME", "Commander")
    role = os.environ.get("APPLY_ROLE", "engineer")
    try:
        orchestrator.run_application(name, role, cv)
        log.info("cycle complete | metrics=%s", db.metrics())
    except Exception as e:
        log.error("cycle error: %s", e)

class H(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        if self.path == "/status":
            try:
                m = db.metrics()
            except Exception:
                m = {}
            m["ok"] = ENGINE_OK
            m["engine"] = "orchestrator" if ENGINE_OK else "offline"
            m["kill_switch_on"] = db.kill_switch_on() if ENGINE_OK else None
            m["time"] = datetime.now(timezone.utc).isoformat()
            self._send(m)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path == "/run":
            Thread(target=run_cycle, daemon=True).start()
            self._send({"ok": True, "msg": "cycle started"}, 202)
        elif self.path == "/kill":
            db.set_kill_switch(True)
            self._send({"ok": True, "kill_switch": True})
        elif self.path == "/resume":
            db.set_kill_switch(False)
            self._send({"ok": True, "kill_switch": False})
        else:
            self.send_response(404); self.end_headers()

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    sched = BackgroundScheduler()
    sched.add_job(run_cycle, "cron", hour=23, minute=0)
    sched.start()
    log.info("service up on :%s  engine_ok=%s", PORT, ENGINE_OK)
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()

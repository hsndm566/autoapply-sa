#!/usr/bin/env python3
"""Lightweight health endpoint for Hermes to poll the Azure backend.
Run on VM: python3 health.py  (or via cron). Exposes /status via a tiny HTTP server.
"""
import json, os, subprocess, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "/opt/autoapply"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            # check python + last run log
            status = {
                "ok": True,
                "time": datetime.datetime.utcnow().isoformat(),
                "repo": os.path.exists(BASE),
                "python": subprocess.run(["python3","--version"],capture_output=True,text=True).stderr.strip(),
                "cron": "0 23 * * * orchestrator.py",
            }
            try:
                with open("/var/log/autoapply.log") as f:
                    status["last_run"] = f.read().splitlines()[-3:]
            except: status["last_run"] = "no log yet"
            body = json.dumps(status).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a): pass

if __name__ == "__main__":
    print("health endpoint on :8080/status")
    HTTPServer(("0.0.0.0",8080), H).serve_forever()

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
BRIDGE_TOKEN = os.environ.get("BRIDGE_TOKEN", "").strip()
ALLOWED_SENDERS = {"apply@hsndm.tech", "apply1@hsndm.tech", "apply2@hsndm.tech"}

def brevo_request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3" + path,
        data=data,
        method=method,
        headers={
            "api-key": BREVO_API_KEY,
            "accept": "application/json",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return resp.status, json.loads(raw) if raw else {}

def preflight():
    result = {
        "brevo_account_ok": False,
        "domain_present": False,
        "domain_authenticated": None,
        "domain_verified": None,
        "senders": {},
    }
    if not BREVO_API_KEY:
        result["error"] = "BREVO_API_KEY missing"
        return result

    try:
        status, _ = brevo_request("GET", "/account")
        result["brevo_account_ok"] = status == 200

        _, domains = brevo_request("GET", "/senders/domains")
        for d in domains.get("domains", []):
            name = (d.get("domain_name") or d.get("domain") or d.get("name") or "").lower()
            if name == "hsndm.tech":
                result["domain_present"] = True
                if "authenticated" in d:
                    result["domain_authenticated"] = bool(d.get("authenticated"))
                if "verified" in d:
                    result["domain_verified"] = bool(d.get("verified"))
                break

        _, senders = brevo_request("GET", "/senders")
        by_email = {str(s.get("email") or "").lower(): s for s in senders.get("senders", [])}
        for email in sorted(ALLOWED_SENDERS):
            s = by_email.get(email)
            result["senders"][email] = {
                "present": bool(s),
                "active": None if not s or "active" not in s else bool(s.get("active")),
            }
        return result
    except urllib.error.HTTPError as exc:
        result["error"] = f"Brevo HTTP {exc.code}"
        return result
    except Exception as exc:
        result["error"] = type(exc).__name__
        return result

def send_batch(form):
    token = form.get("token", [""])[0]
    if not BRIDGE_TOKEN or token != BRIDGE_TOKEN:
        return 403, {"ok": False, "error": "forbidden"}

    sender = form.get("sender", [""])[0].strip().lower()
    candidate_name = form.get("candidate_name", [""])[0].strip()
    cv_filename = form.get("cv_filename", [""])[0].strip()
    cv_base64 = form.get("cv_base64", [""])[0].strip()
    messages_json = form.get("messages_json", [""])[0]

    if sender not in ALLOWED_SENDERS:
        return 400, {"ok": False, "error": "sender_not_allowed"}
    if not candidate_name:
        return 400, {"ok": False, "error": "candidate_name_required"}
    if not cv_filename.lower().endswith(".pdf") or not cv_base64:
        return 400, {"ok": False, "error": "valid_pdf_required"}

    try:
        pdf_bytes = base64.b64decode(cv_base64, validate=True)
    except Exception:
        return 400, {"ok": False, "error": "invalid_base64"}
    if not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-4096:]:
        return 400, {"ok": False, "error": "invalid_pdf"}

    try:
        messages = json.loads(messages_json)
    except Exception:
        return 400, {"ok": False, "error": "messages_json_invalid"}
    if not isinstance(messages, list) or not (1 <= len(messages) <= 15):
        return 400, {"ok": False, "error": "batch_must_be_1_to_15"}

    results = []
    for i, m in enumerate(messages, 1):
        recipient = str(m.get("to") or "").strip().lower()
        subject = str(m.get("subject") or "").strip()
        body = str(m.get("body") or "").strip()
        company = str(m.get("company") or "").strip()
        if not recipient or "@" not in recipient or not subject or len(body) < 80 or not company:
            results.append({"index": i, "to": recipient, "company": company, "status": "invalid_message"})
            continue

        payload = {
            "sender": {"email": sender, "name": candidate_name},
            "to": [{"email": recipient}],
            "replyTo": {"email": sender, "name": candidate_name},
            "subject": subject,
            "textContent": body,
            "attachment": [{"name": cv_filename, "content": cv_base64}],
        }
        try:
            _, provider = brevo_request("POST", "/smtp/email", payload)
            message_id = str(provider.get("messageId") or "")
            results.append({"index": i, "to": recipient, "company": company, "status": "accepted", "message_id": message_id})
        except urllib.error.HTTPError as exc:
            results.append({"index": i, "to": recipient, "company": company, "status": "failed", "http_status": exc.code})
        except Exception as exc:
            results.append({"index": i, "to": recipient, "company": company, "status": "failed", "error": type(exc).__name__})

    return 200, {"ok": True, "results": results}

class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, obj):
        body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"ok": True, "service": "autoapply-brevo-bridge"})
        if self.path == "/preflight":
            return self.send_json(200, preflight())
        if self.path == "/admin":
            html = """<!doctype html><html><body><form method='post' action='/send'>
            <input name='token' type='password' placeholder='token'><br>
            <input name='sender' value='apply@hsndm.tech'><br>
            <input name='candidate_name' value='Hasan Adam'><br>
            <input name='cv_filename' value='Hasan-Adam-CV.pdf'><br>
            <textarea name='cv_base64' rows='4' cols='80' placeholder='base64 PDF'></textarea><br>
            <textarea name='messages_json' rows='16' cols='120' placeholder='[{"to":"x@example.com","company":"X","subject":"...","body":"..."}]'></textarea><br>
            <button type='submit'>Send batch</button>
            </form></body></html>"""
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path != "/send":
            return self.send_json(404, {"ok": False, "error": "not_found"})
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        status, obj = send_batch(form)
        self.send_json(status, obj)

    def log_message(self, fmt, *args):
        print(fmt % args)

if __name__ == "__main__":
    print(json.dumps({"startup_preflight": preflight()}))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

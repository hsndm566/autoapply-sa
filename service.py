"""AutoApply SA API service.

This is the public campaign boundary.  It accepts a CV and campaign brief, creates
durable campaign state, exposes status/events, and runs only safe maintenance by
default.  Legacy external execution is disabled unless explicitly configured after
a source-specific upload proof and Auditor verification are in place.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import subprocess
from email.parser import BytesParser
from email.policy import default as email_default_policy
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from apscheduler.schedulers.background import BackgroundScheduler

import bayt_profile_adapter
import campaign_worker
import contact_import
import db
import diversity_queue

try:
    import orchestrator
    ENGINE_OK = True
except Exception as exc:  # Health must stay available even if an optional legacy module fails.
    orchestrator = None
    ENGINE_OK = False
    ENGINE_ERROR = str(exc)
else:
    ENGINE_ERROR = ""

LOG = logging.getLogger("autoapply.api")
PORT = int(os.environ.get("PORT", "8080"))
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_CV_UPLOAD_BYTES", str(5 * 1024 * 1024)))
CV_STORAGE_DIR = Path(os.environ.get("CV_STORAGE_DIR", os.path.join(os.path.dirname(__file__), "data", "cv")))
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "https://hsndm.tech")
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN", "")
JOB_IMPORT_TOKEN = os.environ.get("JOB_IMPORT_TOKEN", "")
ALLOW_LEGACY_EXTERNAL_EXECUTION = os.environ.get("ALLOW_LEGACY_EXTERNAL_EXECUTION", "false").lower() == "true"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(value or "cv").name)[:120] or "cv"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sanitize_text(value: object, limit: int = 250) -> str:
    return str(value or "").strip()[:limit]


class _MultipartPart:
    def __init__(self, *, filename: str | None, payload: bytes) -> None:
        self.filename = filename
        self.file = io.BytesIO(payload)


class _MultipartForm:
    def __init__(self, fields: dict[str, _MultipartPart | str]) -> None:
        self._fields = fields

    def __contains__(self, key: str) -> bool:
        return key in self._fields

    def __getitem__(self, key: str) -> _MultipartPart | str:
        return self._fields[key]

    def getfirst(self, key: str, default: str = "") -> str:
        value = self._fields.get(key, default)
        return value if isinstance(value, str) else default


def _campaign_token(handler: BaseHTTPRequestHandler) -> str:
    return handler.headers.get("X-Campaign-Token", "").strip()


def _is_admin(handler: BaseHTTPRequestHandler) -> bool:
    presented = handler.headers.get("X-Admin-Token", "").strip()
    return bool(ADMIN_API_TOKEN and presented and hmac.compare_digest(presented, ADMIN_API_TOKEN))


def _is_job_importer(handler: BaseHTTPRequestHandler) -> bool:
    presented = handler.headers.get("X-Job-Import-Token", "").strip()
    return bool(JOB_IMPORT_TOKEN and presented and hmac.compare_digest(presented, JOB_IMPORT_TOKEN))


def _store_cv(upload: _MultipartPart | None) -> tuple[str | None, str | None, str | None]:
    if upload is None or not getattr(upload, "filename", None):
        return None, None, None
    name = _safe_name(upload.filename)
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("CV must be PDF, DOC, DOCX, or TXT")
    CV_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="upload-", dir=str(CV_STORAGE_DIR))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as dest:
            shutil.copyfileobj(upload.file, dest, length=1024 * 1024)
        size = temp_path.stat().st_size
        if not size:
            raise ValueError("CV upload was empty")
        if size > MAX_UPLOAD_BYTES:
            raise ValueError(f"CV exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
        final = CV_STORAGE_DIR / f"campaign-cv-{hashlib.sha256(os.urandom(32)).hexdigest()[:20]}{suffix}"
        temp_path.replace(final)
        return str(final), name, _file_sha256(final)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def run_safe_maintenance() -> None:
    try:
        campaign_worker.run_maintenance_cycle()
    except Exception as exc:
        LOG.exception("safe maintenance failed: %s", exc)


def run_legacy_cycle() -> None:
    """Intentionally guarded legacy path. It is never scheduled by default."""
    if not ALLOW_LEGACY_EXTERNAL_EXECUTION:
        LOG.warning("legacy cycle rejected: ALLOW_LEGACY_EXTERNAL_EXECUTION is false")
        return
    if not ENGINE_OK or db.kill_switch_on():
        LOG.warning("legacy cycle skipped: engine=%s kill_switch=%s", ENGINE_OK, db.kill_switch_on())
        return
    cv = os.environ.get("CV_TEXT", "")
    name = os.environ.get("APPLY_NAME", "")
    role = os.environ.get("APPLY_ROLE", "")
    if not (cv and name and role):
        LOG.error("legacy cycle blocked: campaign values are not configured")
        return
    # The legacy engine still has its own Auditor assertion.  This outer service never bypasses it.
    orchestrator.run_application(name, role, cv)


class AutoApplyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        LOG.info("%s - %s", self.address_string(), format % args)

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and origin == CORS_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Campaign-Token, X-Admin-Token, X-Job-Import-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, payload: dict[str, object], code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._send({"ok": False, "error": "not_found"}, HTTPStatus.NOT_FOUND)

    def _forbidden(self) -> None:
        self._send({"ok": False, "error": "forbidden"}, HTTPStatus.FORBIDDEN)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 1024 * 1024:
            raise ValueError("JSON body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _multipart_campaign(self) -> tuple[dict[str, str], _MultipartPart | None]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            data = self._read_json()
            return {key: _sanitize_text(value) for key, value in data.items()}, None
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > MAX_UPLOAD_BYTES + 1024 * 1024:
            raise ValueError("Multipart request is missing or exceeds the upload limit")
        body = self.rfile.read(length)
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii", "strict")
        message = BytesParser(policy=email_default_policy).parsebytes(header + body)
        if not message.is_multipart():
            raise ValueError("Malformed multipart request")
        fields: dict[str, _MultipartPart | str] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                fields[name] = _MultipartPart(filename=filename, payload=payload)
            else:
                charset = part.get_content_charset() or "utf-8"
                fields[name] = payload.decode(charset, errors="replace")
        form = _MultipartForm(fields)
        values: dict[str, str] = {}
        for key in ("candidate_name", "candidate_email", "target_role", "city", "industry", "seniority", "language"):
            if key in form and not getattr(form[key], "filename", None):
                values[key] = _sanitize_text(form.getfirst(key, ""))
        upload = form["cv"] if "cv" in form and isinstance(form["cv"], _MultipartPart) else None
        return values, upload

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in {"/healthz", "/status"}:
            try:
                bayt_handoff = bayt_profile_adapter.queue_summary(db.DB_PATH)
            except Exception as exc:
                bayt_handoff = {"adapter_id": bayt_profile_adapter.ADAPTER_ID, "status": "unavailable", "reason": type(exc).__name__}
            status = {
                "ok": True,
                "time": _utc_now(),
                "engine": "available" if ENGINE_OK else "offline",
                "engine_error": ENGINE_ERROR if not ENGINE_OK else None,
                "kill_switch_on": db.kill_switch_on(),
                "external_execution_enabled": ALLOW_LEGACY_EXTERNAL_EXECUTION,
                "metrics": db.metrics(),
                "health": db.health_snapshot(),
                "bayt_profile_handoff": bayt_handoff,
            }
            self._send(status)
            return
        if path == "/v1/portal-queues/bayt":
            try:
                self._send({"ok": True, "bayt": bayt_profile_adapter.queue_summary(db.DB_PATH)})
            except Exception as exc:
                self._send({"ok": False, "error": "bayt_queue_unavailable", "detail": type(exc).__name__}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        if path == "/v1/portal-queues/diversified":
            try:
                limit = int(parse_qs(parsed.query).get("limit", ["10"])[0])
                ready = bayt_profile_adapter.profile_ready()
                self._send({
                    "ok": True,
                    "queue": diversity_queue.queue_summary(
                        db.DB_PATH, limit=limit, bayt_profile_ready=ready
                    ),
                })
            except ValueError as exc:
                self._send({"ok": False, "error": "invalid_queue_limit", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                LOG.exception("diversified queue unavailable: %s", exc)
                self._send({"ok": False, "error": "diversified_queue_unavailable", "detail": type(exc).__name__}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        parts = [segment for segment in path.split("/") if segment]
        if len(parts) == 3 and parts[:2] == ["v1", "campaigns"]:
            campaign_id = parts[2]
            if not db.campaign_authorized(campaign_id, _campaign_token(self)):
                self._forbidden()
                return
            summary = db.campaign_summary(campaign_id)
            self._send({"ok": True, "campaign": summary or {}})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "campaigns"] and parts[3] == "events":
            campaign_id = parts[2]
            if not db.campaign_authorized(campaign_id, _campaign_token(self)):
                self._forbidden()
                return
            limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
            self._send({"ok": True, "events": db.list_campaign_events(campaign_id, limit)})
            return
        self._not_found()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/v1/campaigns":
                values, upload = self._multipart_campaign()
                required = ("candidate_name", "candidate_email", "target_role")
                missing = [key for key in required if not values.get(key)]
                if missing:
                    self._send({"ok": False, "error": "missing_fields", "fields": missing}, HTTPStatus.BAD_REQUEST)
                    return
                if "@" not in values["candidate_email"]:
                    self._send({"ok": False, "error": "invalid_email"}, HTTPStatus.BAD_REQUEST)
                    return
                cv_path, cv_name, cv_sha = _store_cv(upload)
                campaign, token = db.create_campaign(
                    candidate_name=values["candidate_name"],
                    candidate_email=values["candidate_email"],
                    target_role=values["target_role"],
                    city=values.get("city", ""),
                    industry=values.get("industry", ""),
                    seniority=values.get("seniority", ""),
                    language=values.get("language", ""),
                    cv_path=cv_path,
                    cv_original_name=cv_name,
                    cv_sha256=cv_sha,
                )
                self._send(
                    {
                        "ok": True,
                        "campaign": db.campaign_summary(campaign["id"]),
                        "campaign_access_token": token,
                        "message": "Campaign created. Discovery is safe/read-only until a source has verified CV upload and Auditor approval.",
                    },
                    HTTPStatus.CREATED,
                )
                return

            parts = [segment for segment in path.split("/") if segment]
            if len(parts) == 4 and parts[:2] == ["v1", "campaigns"] and parts[3] in {"start", "pause"}:
                campaign_id, action = parts[2], parts[3]
                if not db.campaign_authorized(campaign_id, _campaign_token(self)):
                    self._forbidden()
                    return
                campaign = db.activate_campaign(campaign_id) if action == "start" else db.pause_campaign(campaign_id)
                self._send({"ok": True, "campaign": db.campaign_summary(campaign_id), "action": action})
                return

            if path == "/v1/admin/portal-handoffs/outcomes":
                if not _is_job_importer(self):
                    self._forbidden()
                    return
                data = self._read_json()
                try:
                    record = db.record_browser_handoff_attempt(
                        str(data.get("url") or ""),
                        str(data.get("status") or ""),
                        str(data.get("detail") or ""),
                    )
                except ValueError as exc:
                    self._send({"ok": False, "error": "invalid_handoff_outcome", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
                    return
                self._send({
                    "ok": True,
                    "submits_applications": False,
                    "record": record,
                })
                return

            if path == "/v1/admin/auditor/review":
                if not _is_job_importer(self):
                    self._forbidden()
                    return
                data = self._read_json()
                system_prompt = str(data.get("system_prompt") or "")
                package = data.get("package")
                if not system_prompt or not isinstance(package, dict):
                    self._send({"ok": False, "error": "system_prompt_and_package_required"}, HTTPStatus.BAD_REQUEST)
                    return
                try:
                    import auditor
                    result = auditor.configured_ai_reviewer(system_prompt, package)
                    required = {"decision", "confidence", "reasons", "required_fixes"}
                    if not isinstance(result, dict) or not required.issubset(result):
                        raise ValueError("reviewer response schema invalid")
                    self._send({"ok": True, "review": result})
                except Exception as exc:
                    LOG.warning("Auditor review bridge unavailable: %s", type(exc).__name__)
                    self._send({"ok": False, "error": "reviewer_unavailable", "reason": type(exc).__name__}, HTTPStatus.SERVICE_UNAVAILABLE)
                return

            if path == "/v1/admin/auditor/self-test":
                if not _is_job_importer(self):
                    self._forbidden()
                    return
                try:
                    import auditor
                    reviewer_result = auditor.configured_ai_reviewer(
                        "Return only a JSON object with decision, confidence, reasons, and required_fixes.",
                        {"kind": "auditor_connectivity_self_test", "external_action": "none"},
                    )
                    required = {"decision", "confidence", "reasons", "required_fixes"}
                    if not isinstance(reviewer_result, dict) or not required.issubset(reviewer_result):
                        raise ValueError("reviewer response schema invalid")
                    self._send({"ok": True, "reviewer": "available", "schema_valid": True})
                except Exception as exc:
                    LOG.warning("Auditor connectivity self-test unavailable: %s", type(exc).__name__)
                    self._send({"ok": False, "reviewer": "unavailable", "reason": type(exc).__name__}, HTTPStatus.SERVICE_UNAVAILABLE)
                return

            if path == "/v1/admin/jobs/import":
                if not _is_job_importer(self):
                    self._forbidden()
                    return
                data = self._read_json()
                rows = data.get("jobs")
                if not isinstance(rows, list) or not rows:
                    self._send({"ok": False, "error": "jobs_list_required"}, HTTPStatus.BAD_REQUEST)
                    return
                if len(rows) > 500:
                    self._send({"ok": False, "error": "jobs_limit_exceeded"}, HTTPStatus.BAD_REQUEST)
                    return
                counts = db.import_discovered_jobs(rows)
                self._send({"ok": True, "import": counts, "external_execution_enabled": False})
                return

            if path == "/v1/admin/contacts/import":
                if not _is_admin(self):
                    self._forbidden()
                    return
                data = self._read_json()
                rows = data.get("contacts")
                if not isinstance(rows, list) or not rows:
                    self._send({"ok": False, "error": "contacts_list_required"}, HTTPStatus.BAD_REQUEST)
                    return
                if len(rows) > 2000:
                    self._send({"ok": False, "error": "contacts_limit_exceeded"}, HTTPStatus.BAD_REQUEST)
                    return
                source = _sanitize_text(data.get("verification_source"), 200)
                counts = contact_import.import_contact_rows(
                    rows,
                    verification_source=source,
                    mark_verified=data.get("mark_verified") is True,
                )
                self._send({"ok": True, "import": counts, "delivery_enabled": False})
                return

            if path in {"/run", "/kill", "/resume"}:
                if not _is_admin(self):
                    self._forbidden()
                    return
                if path == "/run":
                    threading.Thread(target=run_legacy_cycle, daemon=True).start()
                    self._send({"ok": True, "message": "legacy cycle request accepted", "external_execution_enabled": ALLOW_LEGACY_EXTERNAL_EXECUTION}, HTTPStatus.ACCEPTED)
                elif path == "/kill":
                    db.set_kill_switch(True)
                    self._send({"ok": True, "kill_switch": True})
                else:
                    db.set_kill_switch(False)
                    self._send({"ok": True, "kill_switch": False})
                return
            self._not_found()
        except (ValueError, json.JSONDecodeError) as exc:
            self._send({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            LOG.exception("request failed: %s", exc)
            self._send({"ok": False, "error": "internal_error"}, HTTPStatus.INTERNAL_SERVER_ERROR)


def build_server(port: int = PORT) -> ThreadingHTTPServer:
    db.initialize()
    return ThreadingHTTPServer(("0.0.0.0", port), AutoApplyHandler)


def start_heartbeat():
    try:
        LOG.info("Starting background heartbeat monitor...")
        subprocess.Popen(["python3", "-u", "heartbeat_monitor.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except Exception as exc:
        LOG.error("Failed to start heartbeat monitor: %s", exc)

def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    db.initialize()
    # Establish local observability at boot without delaying health checks on public listing APIs.
    campaign_worker.run_maintenance_cycle(discover_campaigns=False)
    
    # Start the autonomous application heartbeat in the background
    threading.Thread(target=start_heartbeat, daemon=True).start()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_safe_maintenance, "interval", minutes=5, id="safe-maintenance", replace_existing=True)
    scheduler.start()
    LOG.info("service up on :%s engine_ok=%s external_execution_enabled=%s", PORT, ENGINE_OK, ALLOW_LEGACY_EXTERNAL_EXECUTION)
    build_server().serve_forever()


if __name__ == "__main__":
    main()

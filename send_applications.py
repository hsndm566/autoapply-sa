"""Three-client application preflight for AutoApply SA.

This script does not send mail directly. Repository governance requires live
applications to be queued with campaign_email.prepare_audited_campaign_email()
and delivered only by email_dispatcher after a current Auditor approval.

Use --dry-run to validate client mapping, PDF artifacts, recipients, MX records,
deduplication, and warm-up limits without creating a send intent or contacting
any recipient.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import os
from collections import Counter
from pathlib import Path
from typing import Any

import dns.resolver


MAX_PER_IDENTITY_PER_RUN = 5
MAX_TOTAL_PER_RUN = 15
WAIT_BETWEEN_SENDS_SECONDS = (120, 240)
REQUIRED_CLIENT_COLUMNS = {"sender_email", "client_name", "cv_file"}
REQUIRED_JOB_COLUMNS = {"recipient_email", "company", "role", "city", "client_id"}
ALLOWED_SENDERS = {
    "apply@hsndm.tech",
    "apply1@hsndm.tech",
    "apply2@hsndm.tech",
}
OPTOUT_LINE = "If you'd prefer not to receive future applications from this platform, reply STOP."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", default="clients.csv")
    parser.add_argument("--jobs", default="jobs.csv")
    parser.add_argument("--tracking", default="tracking.csv")
    parser.add_argument("--cvs-dir", default="cvs")
    parser.add_argument("--dry-run", action="store_true", help="Validate without queueing or sending.")
    parser.add_argument("--limit", type=int, default=MAX_TOTAL_PER_RUN)
    return parser.parse_args()


def validate_sender_domain() -> None:
    """Reject a mismatched configured sender domain without requiring a secret for local tests."""
    configured = os.environ.get("SENDER_DOMAIN", "").strip().lower()
    if configured and configured != "hsndm.tech":
        raise ValueError("SENDER_DOMAIN must be hsndm.tech for the configured client identities")


def require_columns(fieldnames: list[str] | None, required: set[str], path: Path) -> None:
    missing = required.difference(fieldnames or [])
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")


def normalize_email(value: str, field: str) -> str:
    email = value.strip().lower()
    if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError(f"Invalid {field}: {value!r}")
    return email


def load_clients(path: Path) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames, REQUIRED_CLIENT_COLUMNS, path)
        clients: dict[int, dict[str, str]] = {}
        for client_id, row in enumerate(reader, start=1):
            sender_email = normalize_email(str(row["sender_email"]), "sender_email")
            client_name = str(row["client_name"] or "").strip()
            cv_file = str(row["cv_file"] or "").strip()
            if sender_email not in ALLOWED_SENDERS:
                raise ValueError(f"client_id {client_id} has an unsupported sender")
            if not client_name:
                raise ValueError(f"client_id {client_id} has no client_name")
            if Path(cv_file).name != cv_file or not cv_file.lower().endswith(".pdf"):
                raise ValueError(f"client_id {client_id} must use a PDF in cvs/")
            clients[client_id] = {"sender_email": sender_email, "client_name": client_name, "cv_file": cv_file}
    if set(clients) != {1, 2, 3}:
        raise ValueError("clients.csv must contain exactly three client rows")
    return clients


def load_jobs(path: Path, clients: dict[int, dict[str, str]]) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames, REQUIRED_JOB_COLUMNS, path)
        jobs: list[dict[str, Any]] = []
        for number, row in enumerate(reader, start=2):
            client_id = int(str(row["client_id"] or "").strip())
            if client_id not in clients:
                raise ValueError(f"jobs.csv row {number} references unknown client_id {client_id}")
            recipient_email = normalize_email(str(row["recipient_email"]), "recipient_email")
            company = str(row["company"] or "").strip()
            role = str(row["role"] or "").strip()
            city = str(row["city"] or "").strip()
            jobs.append(
                {
                    "recipient_email": recipient_email,
                    "company": company,
                    "role": role,
                    "city": city,
                    "client_id": client_id,
                    "eligible": bool(company and role),
                    "validation_error": "missing explicit company or role" if not company or not role else "",
                }
            )
    return jobs


def load_tracking(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_columns(reader.fieldnames, {"recipient_email"}, path)
        return {str(row.get("recipient_email") or "").strip().lower() for row in reader if row.get("recipient_email")}


def deterministic_sender(job: dict[str, Any], clients: dict[int, dict[str, str]]) -> str:
    """A client_id always maps to the same sender identity, independent of run order."""
    return clients[int(job["client_id"])]["sender_email"]


def has_valid_mx(email: str) -> bool:
    try:
        answers = dns.resolver.resolve(email.rsplit("@", 1)[1], "MX")
        return bool(answers)
    except (dns.resolver.DNSException, ValueError):
        return False


def read_valid_pdf(cvs_dir: Path, cv_file: str) -> bytes:
    cv_path = cvs_dir / cv_file
    if not cv_path.is_file():
        raise FileNotFoundError(f"CV file missing: {cv_path}")
    content = cv_path.read_bytes()
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-4096:]:
        raise ValueError(f"CV is not a complete approved PDF: {cv_path}")
    if not content:
        raise ValueError(f"CV is empty: {cv_path}")
    return content


def brevo_attachment(cvs_dir: Path, cv_file: str) -> dict[str, str]:
    """Return the exact Base64 attachment format only for an approved PDF artifact.

    Live use is intentionally delegated to the repository's audited dispatcher.
    """
    return {"name": "CV.pdf", "content": base64.b64encode(read_valid_pdf(cvs_dir, cv_file)).decode("ascii")}


def build_cover_letter(client_name: str, company: str, role: str, city: str) -> str:
    """Build factual, deterministic template text without generating claims."""
    location = f" in {html.escape(city)}" if city else ""
    return (
        f"Dear {html.escape(company)} Hiring Team,\n\n"
        f"I am writing to apply for the {html.escape(role)} role{location} at {html.escape(company)}. "
        "My CV is attached for your review.\n\n"
        "Kind regards,\n"
        f"{html.escape(client_name)}\n\n"
        f"{OPTOUT_LINE}"
    )


def select_batch(jobs: list[dict[str, Any]], tracked: set[str], clients: dict[int, dict[str, str]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen = set(tracked)
    for job in jobs:
        recipient = str(job["recipient_email"])
        sender = deterministic_sender(job, clients)
        if (
            not job.get("eligible", True)
            or recipient in seen
            or counts[sender] >= MAX_PER_IDENTITY_PER_RUN
            or len(selected) >= min(limit, MAX_TOTAL_PER_RUN)
        ):
            continue
        selected.append(job)
        seen.add(recipient)
        counts[sender] += 1
    return selected


def preflight(selected: list[dict[str, Any]], clients: dict[int, dict[str, str]], cvs_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    ready: list[dict[str, Any]] = []
    blocked: list[str] = []
    for job in selected:
        client = clients[int(job["client_id"])]
        try:
            read_valid_pdf(cvs_dir, client["cv_file"])
            if not has_valid_mx(str(job["recipient_email"])):
                raise ValueError("recipient domain has no MX record")
            ready.append(job)
        except (FileNotFoundError, ValueError) as error:
            blocked.append(f"{job['recipient_email']}: {error}")
    return ready, blocked


def main() -> None:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit(
            "Direct sending is blocked by repository governance. Use --dry-run for preflight; "
            "live delivery requires verified contacts, real approved PDFs, job URLs, current Auditor approval, "
            "and email_dispatcher.dispatch_pending()."
        )
    validate_sender_domain()
    clients = load_clients(Path(args.clients))
    jobs = load_jobs(Path(args.jobs), clients)
    ineligible_count = sum(1 for job in jobs if not job.get("eligible", True))
    selected = select_batch(jobs, load_tracking(Path(args.tracking)), clients, args.limit)
    ready, blocked = preflight(selected, clients, Path(args.cvs_dir))
    per_sender = Counter(deterministic_sender(job, clients) for job in ready)
    print(
        f"selected={len(selected)} ready={len(ready)} blocked={len(blocked)} "
        f"ineligible_rows={ineligible_count} per_sender={dict(per_sender)}"
    )
    for error in blocked:
        print(f"BLOCKED: {error}")
    for job in ready:
        client = clients[int(job["client_id"])]
        digest = hashlib.sha256(str(job["recipient_email"]).encode()).hexdigest()[:12]
        print(f"READY: sender={client['sender_email']} recipient_hash={digest} client_id={job['client_id']}")


if __name__ == "__main__":
    main()

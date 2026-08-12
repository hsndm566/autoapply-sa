"""Fail-closed Greenhouse browser upload proof adapter.

This module deliberately has no scheduler and no public HTTP endpoint.  It receives
an already-authorized, job-specific application plan and drives one Greenhouse form
through an injected browser session.  The default configuration blocks before the
browser is touched; an explicit deployment setting and a current Auditor approval
are both required for an actual submit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

import auditor
import db

ADAPTER_ID = "greenhouse_playwright_v1"
ADAPTER_VERSION = "1.0.0"
CONFIRMATION_PATTERNS = (
    "thank you for applying",
    "application submitted",
    "application received",
    "thank you for your application",
)
SAFE_FORM_FIELD = re.compile(r"^[A-Za-z0-9_\[\]-]{1,128}$")


@dataclass(frozen=True)
class ProofResult:
    status: str
    reason: str
    source: str = "greenhouse"
    adapter_id: str = ADAPTER_ID
    adapter_version: str = ADAPTER_VERSION
    job_url: str = ""
    post_submit_url: str = ""
    cv_sha256: str = ""
    selected_filename: str = ""
    form_fingerprint: str = ""
    confirmation_digest: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def upload_selected(self) -> bool:
        return self.status in {"upload_selected", "submitted_confirmed", "submitted_unconfirmed"}

    @property
    def submitted_confirmed(self) -> bool:
        return self.status == "submitted_confirmed"

    @property
    def side_effect_possible(self) -> bool:
        return self.status in {"submitted_confirmed", "submitted_unconfirmed"}

    def as_evidence(self) -> dict[str, Any]:
        data = asdict(self)
        # Never put raw form values, page HTML, or a CV path into durable evidence.
        return data


@dataclass(frozen=True)
class GreenhouseUploadRequest:
    """An explicit, job-specific form plan.

    ``form_values`` must have been mapped from the job's published Greenhouse
    questions.  The adapter fills only these supplied field names and never invents
    answers.  ``submit_selector`` is intentionally required to avoid guessing which
    control performs the external action.
    """

    campaign_id: str
    campaign_job_id: str
    application_id: str
    application_package: Mapping[str, Any]
    auditor_approval_token: str
    job_url: str
    cv_path: str
    form_values: Mapping[str, str]
    submit_selector: str
    file_input_selector: str = 'input[type="file"]'


class GreenhouseBrowserSession(Protocol):
    """Minimal browser contract; tests can supply a deterministic fake session."""

    def goto(self, url: str) -> None: ...
    def count(self, selector: str) -> int: ...
    def input_type(self, selector: str) -> str: ...
    def set_input_files(self, selector: str, path: str) -> None: ...
    def selected_filename(self, selector: str) -> str: ...
    def fill_by_name(self, name: str, value: str) -> None: ...
    def unresolved_required_fields(self) -> list[str]: ...
    def click(self, selector: str) -> None: ...
    def current_url(self) -> str: ...
    def visible_text(self) -> str: ...


class PlaywrightGreenhouseSession:
    """Thin production wrapper around a Playwright Page, imported only when used."""

    def __init__(self, page: Any) -> None:
        self.page = page

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    def count(self, selector: str) -> int:
        return int(self.page.locator(selector).count())

    def input_type(self, selector: str) -> str:
        return str(self.page.locator(selector).first.get_attribute("type") or "").lower()

    def set_input_files(self, selector: str, path: str) -> None:
        self.page.locator(selector).first.set_input_files(path)

    def selected_filename(self, selector: str) -> str:
        return str(self.page.locator(selector).first.evaluate("element => element.files?.[0]?.name || ''"))

    def fill_by_name(self, name: str, value: str) -> None:
        if not SAFE_FORM_FIELD.fullmatch(name):
            raise ValueError(f"unsafe Greenhouse form field name: {name}")
        selector = f'[name="{name}"]'
        if self.count(selector) != 1:
            raise ValueError(f"Greenhouse field must resolve exactly once: {name}")
        locator = self.page.locator(selector)
        field_type = str(locator.get_attribute("type") or "").lower()
        if field_type == "checkbox":
            if str(value).lower() not in {"true", "1", "yes", "on"}:
                raise ValueError(f"checkbox field requires an explicit true value: {name}")
            locator.check()
        elif field_type == "radio":
            locator.check()
        elif field_type == "file":
            raise ValueError("CV file inputs may only be set through the verified file control")
        else:
            locator.fill(str(value))

    def unresolved_required_fields(self) -> list[str]:
        return list(self.page.locator("[required]").evaluate_all("""
            nodes => nodes.filter(node => {
                if (node.disabled) return false;
                const type = (node.type || '').toLowerCase();
                if (type === 'hidden') return false;
                if (type === 'checkbox' || type === 'radio') return !node.checked;
                if (type === 'file') return !(node.files && node.files.length > 0);
                return !String(node.value || '').trim();
            }).map(node => node.name || node.id || node.tagName.toLowerCase())
        """))

    def click(self, selector: str) -> None:
        if self.count(selector) != 1:
            raise ValueError("submit selector must resolve exactly once")
        self.page.locator(selector).click()
        self.page.wait_for_load_state("domcontentloaded")

    def current_url(self) -> str:
        return str(self.page.url)

    def visible_text(self) -> str:
        return str(self.page.locator("body").inner_text()[:12000])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(*, job_url: str, file_input_selector: str, form_values: Mapping[str, str]) -> str:
    material = {
        "job_url": job_url,
        "file_input_selector": file_input_selector,
        "field_names": sorted(str(name) for name in form_values),
        "adapter": ADAPTER_ID,
        "version": ADAPTER_VERSION,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_greenhouse_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.netloc in {"boards.greenhouse.io", "job-boards.greenhouse.io"}


def _confirmation_digest(text: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    lowered = normalized.lower()
    if not any(pattern in lowered for pattern in CONFIRMATION_PATTERNS):
        return "", ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest(), normalized[:300]


class GreenhouseUploadProofAdapter:
    """Select a real CV file, submit only after a recheck, and capture evidence.

    Live submits are *disabled by default* even if this class is instantiated.  The
    execution process must set ``ALLOW_GREENHOUSE_LIVE_SUBMISSION=true`` only after
    offline tests and a separately reviewed source activation.  This adapter does
    not set that variable, modify the source registry, or promote a source itself.
    """

    def __init__(self, session: GreenhouseBrowserSession, *, live_submission_enabled: bool | None = None) -> None:
        self.session = session
        self.live_submission_enabled = (
            os.environ.get("ALLOW_GREENHOUSE_LIVE_SUBMISSION", "false").lower() == "true"
            if live_submission_enabled is None
            else bool(live_submission_enabled)
        )

    def prove(self, request: GreenhouseUploadRequest) -> ProofResult:
        if not self.live_submission_enabled:
            return ProofResult(status="blocked", reason="GREENHOUSE_LIVE_SUBMISSION_DISABLED", job_url=request.job_url)
        if not _safe_greenhouse_url(request.job_url):
            return ProofResult(status="blocked", reason="GREENHOUSE_URL_NOT_ALLOWED", job_url=request.job_url)
        if not request.submit_selector.strip():
            return ProofResult(status="blocked", reason="SUBMIT_SELECTOR_REQUIRED", job_url=request.job_url)

        cv = Path(request.cv_path).expanduser()
        if not cv.is_file() or cv.stat().st_size == 0:
            return ProofResult(status="blocked", reason="CV_ARTIFACT_UNAVAILABLE", job_url=request.job_url)
        declared_cv = str(dict(request.application_package.get("candidate", {})).get("cv_path", ""))
        if Path(declared_cv).expanduser() != cv:
            return ProofResult(status="blocked", reason="CV_PATH_DOES_NOT_MATCH_AUDITED_PACKAGE", job_url=request.job_url)
        submission = dict(request.application_package.get("submission", {}))
        if submission.get("channel") != "portal" or submission.get("cv_transport") != "portal_file_upload_verified":
            return ProofResult(status="blocked", reason="PACKAGE_NOT_DECLARED_AS_VERIFIED_PORTAL_UPLOAD", job_url=request.job_url)
        if str(submission.get("source", "")).lower() != "greenhouse":
            return ProofResult(status="blocked", reason="PACKAGE_SOURCE_IS_NOT_GREENHOUSE", job_url=request.job_url)

        # This is deliberately adjacent to the only click that can submit.  Any
        # changed package, stale token, or missing AI decision stops before click.
        try:
            auditor.assert_execution_allowed(request.application_id, request.application_package, request.auditor_approval_token)
        except PermissionError as exc:
            return ProofResult(status="blocked", reason=f"AUDITOR_RECHECK_FAILED: {exc}", job_url=request.job_url)

        cv_sha = _sha256_file(cv)
        form_fp = _fingerprint(job_url=request.job_url, file_input_selector=request.file_input_selector, form_values=request.form_values)
        try:
            self.session.goto(request.job_url)
            if self.session.count(request.file_input_selector) != 1:
                return ProofResult(status="blocked", reason="FILE_INPUT_MUST_RESOLVE_EXACTLY_ONCE", job_url=request.job_url, cv_sha256=cv_sha, form_fingerprint=form_fp)
            if self.session.input_type(request.file_input_selector) != "file":
                return ProofResult(status="blocked", reason="FILE_CONTROL_TYPE_INVALID", job_url=request.job_url, cv_sha256=cv_sha, form_fingerprint=form_fp)
            self.session.set_input_files(request.file_input_selector, str(cv))
            selected = self.session.selected_filename(request.file_input_selector)
            if selected != cv.name:
                return ProofResult(status="blocked", reason="CV_SELECTION_NOT_CONFIRMED", job_url=request.job_url, cv_sha256=cv_sha, form_fingerprint=form_fp)
            for name, value in request.form_values.items():
                self.session.fill_by_name(str(name), str(value))
            unresolved = self.session.unresolved_required_fields()
            if unresolved:
                return ProofResult(
                    status="upload_selected",
                    reason="UNMAPPED_REQUIRED_FIELDS",
                    job_url=request.job_url,
                    cv_sha256=cv_sha,
                    selected_filename=selected,
                    form_fingerprint=form_fp,
                    evidence={"unresolved_fields": unresolved[:20]},
                )

            # A second recheck prevents approval expiry or package tampering during form completion.
            auditor.assert_execution_allowed(request.application_id, request.application_package, request.auditor_approval_token)
            self.session.click(request.submit_selector)
            post_url = self.session.current_url()
            digest, excerpt = _confirmation_digest(self.session.visible_text())
            if not digest:
                return ProofResult(
                    status="submitted_unconfirmed",
                    reason="POST_SUBMIT_CONFIRMATION_NOT_RECOGNISED",
                    job_url=request.job_url,
                    post_submit_url=post_url,
                    cv_sha256=cv_sha,
                    selected_filename=selected,
                    form_fingerprint=form_fp,
                    evidence={"post_submit_url_changed": post_url != request.job_url},
                )
            result = ProofResult(
                status="submitted_confirmed",
                reason="GREENHOUSE_POST_SUBMIT_CONFIRMATION_CAPTURED",
                job_url=request.job_url,
                post_submit_url=post_url,
                cv_sha256=cv_sha,
                selected_filename=selected,
                form_fingerprint=form_fp,
                confirmation_digest=digest,
                evidence={"confirmation_excerpt": excerpt, "post_submit_url_changed": post_url != request.job_url},
            )
            self._record_campaign_evidence(request, result)
            return result
        except Exception as exc:
            return ProofResult(
                status="blocked",
                reason=f"BROWSER_PROOF_FAILED: {type(exc).__name__}",
                job_url=request.job_url,
                cv_sha256=cv_sha,
                form_fingerprint=form_fp,
            )

    @staticmethod
    def _record_campaign_evidence(request: GreenhouseUploadRequest, result: ProofResult) -> None:
        if request.campaign_id:
            db.record_evidence(
                request.campaign_id,
                "greenhouse_submit_confirmation",
                result.confirmation_digest,
                campaign_job_id=request.campaign_job_id or None,
                metadata=result.as_evidence(),
            )
            db.add_campaign_event(
                request.campaign_id,
                "portal_submission_confirmed",
                "info",
                "Greenhouse post-submit confirmation captured by the verified upload adapter.",
                {"campaign_job_id": request.campaign_job_id, "adapter": ADAPTER_ID},
            )


__all__ = [
    "ADAPTER_ID", "ADAPTER_VERSION", "GreenhouseUploadProofAdapter", "GreenhouseUploadRequest",
    "PlaywrightGreenhouseSession", "ProofResult",
]

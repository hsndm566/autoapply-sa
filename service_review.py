#!/usr/bin/env python3
"""AutoApply API service with campaign-scoped human review and submit routes.

This adapter subclasses the existing service handler instead of duplicating the
large campaign API. Existing endpoints continue to use ``service.py``. Review
and explicit human-triggered submission are intercepted here.
"""
from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import db
import review_runtime
import service
import submission_runtime
from submit_gate import SubmissionRefused

LOG = logging.getLogger("autoapply.review.api")


def _parts(path: str) -> list[str]:
    return [unquote(segment) for segment in path.split("/") if segment]


class ApprovalAutoApplyHandler(service.AutoApplyHandler):
    def _campaign_review_context(self, campaign_id: str):
        if not db.campaign_authorized(campaign_id, service._campaign_token(self)):
            self._forbidden()
            return None
        try:
            review_service = review_runtime.service_for_campaign(campaign_id)
            actor = review_runtime.actor_for_campaign(campaign_id)
        except LookupError:
            self._not_found()
            return None
        return review_service, actor

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = _parts(path)
        if len(parts) == 5 and parts[:2] == ["v1", "campaigns"] and parts[3:] == ["review", "queue"]:
            campaign_id = parts[2]
            context = self._campaign_review_context(campaign_id)
            if context is None:
                return
            review_service, _actor = context
            try:
                self._send({"ok": True, "queue": review_service.queue()})
            except Exception as exc:
                LOG.exception("review queue failed: %s", exc)
                self._send({"ok": False, "error": "review_queue_unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        parts = _parts(path)
        # /v1/campaigns/{campaign_id}/review/{source}/{posting_id}/{action}
        if len(parts) == 7 and parts[:2] == ["v1", "campaigns"] and parts[3] == "review":
            campaign_id, source, posting_id, action = parts[2], parts[4], parts[5], parts[6]
            if action not in {"draft", "approve", "reject", "submit"}:
                self._not_found()
                return
            context = self._campaign_review_context(campaign_id)
            if context is None:
                return
            review_service, actor = context
            try:
                if action == "submit":
                    # Authentication and campaign ownership were checked above.
                    # The runtime reloads the persisted record and re-runs the
                    # fail-closed gate before any adapter can touch an employer.
                    result = submission_runtime.submit_approved(campaign_id, source, posting_id)
                    code = HTTPStatus.OK if result.get("status") == "submitted_verified" else HTTPStatus.CONFLICT
                    self._send({"ok": result.get("status") == "submitted_verified", "result": result}, code)
                    return

                body = self._read_json()
                if action == "draft":
                    rec = review_service.draft(source, posting_id, lang=str(body.get("lang") or "en"))
                    self._send({"ok": True, "state": rec.get("_state"), "record": rec})
                    return
                if action == "approve":
                    # Actor comes from authenticated campaign context. Any
                    # approved_by field supplied by a client is ignored.
                    rec = review_service.approve(
                        source,
                        posting_id,
                        approved_by=actor,
                        edited_letter=body.get("cover_letter") if isinstance(body.get("cover_letter"), str) else None,
                        edited_subject=body.get("subject") if isinstance(body.get("subject"), str) else None,
                    )
                    self._send(
                        {
                            "ok": True,
                            "state": rec.get("_state"),
                            "approved_by": actor,
                            "approval_digest": (rec.get("_draft") or {}).get("approval_digest"),
                        }
                    )
                    return
                rec = review_service.reject(
                    source,
                    posting_id,
                    rejected_by=actor,
                    note=str(body.get("note") or "")[:1000],
                )
                self._send({"ok": True, "state": rec.get("_state")})
                return
            except SubmissionRefused as exc:
                self._send(
                    {"ok": False, "error": "submission_refused", "detail": exc.reason},
                    HTTPStatus.CONFLICT,
                )
                return
            except LookupError:
                self._not_found()
                return
            except PermissionError as exc:
                self._send({"ok": False, "error": "forbidden", "detail": str(exc)[:300]}, HTTPStatus.FORBIDDEN)
                return
            except (ValueError, json.JSONDecodeError) as exc:
                self._send({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except RuntimeError as exc:
                LOG.warning("review/submission runtime unavailable: %s", type(exc).__name__)
                self._send({"ok": False, "error": "review_runtime_unavailable", "detail": str(exc)[:300]}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            except Exception as exc:
                LOG.exception("review action failed: %s", exc)
                self._send({"ok": False, "error": "review_action_failed"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
        super().do_POST()


def build_server(port: int = service.PORT) -> ThreadingHTTPServer:
    db.initialize()
    return ThreadingHTTPServer(("0.0.0.0", port), ApprovalAutoApplyHandler)


def main() -> None:
    # Reuse the existing boot sequence, scheduler, maintenance and health logic.
    service.build_server = build_server
    service.main()


if __name__ == "__main__":
    main()

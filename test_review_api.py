from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import campaign_worker
import db
import review_runtime
import service_review
from review_store import CampaignReviewStore


GOOD = {
    "match_score": 80,
    "evidence": ["Advanced Excel and inventory planning"],
    "gaps": ["No forecasting ownership stated"],
    "subject": "Application for Operations Analyst",
    "cover_letter": "I have advanced Excel and inventory planning experience.",
    "cv_highlights": ["Advanced Excel"],
}


class ReviewApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = db.DB_PATH
        self.old_complete = review_runtime.complete
        self.old_profile_loader = review_runtime.profile_loader
        self.old_groq = os.environ.get("GROQ_API_KEY")
        self.old_auto_draft = os.environ.get("AUTO_DRAFT_ENABLED")
        db.DB_PATH = f"{self.tmp.name}/review.db"
        db.initialize()

        review_runtime.complete = lambda _prompt: json.dumps(GOOD)
        review_runtime.profile_loader = lambda _rec: {
            "full_text": "Candidate has advanced Excel and inventory planning experience.",
            "email": "candidate@example.com",
        }

        self.server = service_review.build_server(0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        review_runtime.complete = self.old_complete
        review_runtime.profile_loader = self.old_profile_loader
        db.DB_PATH = self.old_db
        if self.old_groq is None:
            os.environ.pop("GROQ_API_KEY", None)
        else:
            os.environ["GROQ_API_KEY"] = self.old_groq
        if self.old_auto_draft is None:
            os.environ.pop("AUTO_DRAFT_ENABLED", None)
        else:
            os.environ["AUTO_DRAFT_ENABLED"] = self.old_auto_draft
        self.tmp.cleanup()

    def request(self, method: str, path: str, body=None, token: str = ""):
        payload = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        if token:
            headers["X-Campaign-Token"] = token
        req = Request(f"http://127.0.0.1:{self.port}{path}", data=payload, method=method, headers=headers)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def create_campaign_job(self, email="candidate@example.com"):
        campaign, token = db.create_campaign(
            candidate_name="Review Candidate",
            candidate_email=email,
            target_role="Operations Analyst",
        )
        job_id, _ = db.add_campaign_job(
            campaign["id"],
            company="Example Co",
            title="Operations Analyst",
            job_url="https://jobs.example.com/1",
            source="greenhouse",
            path_state="portal_upload_verified",
        )
        return campaign, token, job_id

    def test_review_queue_requires_campaign_auth(self):
        campaign, token, _job_id = self.create_campaign_job()
        path = f"/v1/campaigns/{campaign['id']}/review/queue"
        status, _body = self.request("GET", path)
        self.assertEqual(status, 403)
        status, body = self.request("GET", path, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(body["queue"]), 1)
        self.assertEqual(body["queue"][0]["state"], "path_verified")

    def test_cross_campaign_token_cannot_read_queue(self):
        _campaign_a, token_a, _ = self.create_campaign_job("a@example.com")
        campaign_b, _token_b, _ = self.create_campaign_job("b@example.com")
        status, _body = self.request(
            "GET",
            f"/v1/campaigns/{campaign_b['id']}/review/queue",
            token=token_a,
        )
        self.assertEqual(status, 403)

    def test_draft_then_approve_uses_server_derived_actor(self):
        campaign, token, job_id = self.create_campaign_job()
        base = f"/v1/campaigns/{campaign['id']}/review/greenhouse/{job_id}"
        status, drafted = self.request("POST", base + "/draft", {"lang": "en"}, token)
        self.assertEqual(status, 200)
        self.assertEqual(drafted["state"], "drafted")

        status, approved = self.request(
            "POST",
            base + "/approve",
            {"approved_by": "forged-user", "cover_letter": "I have advanced Excel experience."},
            token,
        )
        self.assertEqual(status, 200)
        self.assertEqual(approved["state"], "audit_approved")
        self.assertNotEqual(approved["approved_by"], "forged-user")
        self.assertIn(campaign["id"], approved["approved_by"])
        self.assertTrue(approved["approval_digest"])

    def test_unauthenticated_approve_is_refused(self):
        campaign, token, job_id = self.create_campaign_job()
        base = f"/v1/campaigns/{campaign['id']}/review/greenhouse/{job_id}"
        status, _ = self.request("POST", base + "/draft", {"lang": "en"}, token)
        self.assertEqual(status, 200)
        status, _ = self.request("POST", base + "/approve", {})
        self.assertEqual(status, 403)

    def test_nonexistent_review_record_returns_404(self):
        campaign, token, _job_id = self.create_campaign_job()
        status, _ = self.request(
            "POST",
            f"/v1/campaigns/{campaign['id']}/review/greenhouse/missing/draft",
            {"lang": "en"},
            token,
        )
        self.assertEqual(status, 404)

    def test_autonomous_worker_drafts_but_never_approves_or_submits(self):
        campaign, _token, job_id = self.create_campaign_job()
        db.activate_campaign(campaign["id"])
        os.environ["GROQ_API_KEY"] = "test-key-present"
        os.environ["AUTO_DRAFT_ENABLED"] = "true"

        result = campaign_worker.draft_verified_campaign_jobs(max_drafts=1)
        self.assertEqual(result["drafted"], 1)

        rec = CampaignReviewStore(campaign["id"]).get_record("greenhouse", job_id)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["_state"], "drafted")
        self.assertIsNone(rec["_draft"]["approved_by"])
        self.assertNotIn("_submission", rec)
        with db.connection() as c:
            self.assertEqual(0, c.execute("SELECT COUNT(*) AS n FROM application_evidence WHERE campaign_id=?", (campaign["id"],)).fetchone()["n"])


if __name__ == "__main__":
    unittest.main()

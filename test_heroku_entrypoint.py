from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import db
import heroku_entrypoint
import service


class HerokuEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old_db_path = db.DB_PATH
        self.old_cv_dir = service.CV_STORAGE_DIR
        self.old_create = db.create_campaign
        self.old_get = db.get_campaign
        db.DB_PATH = str(Path(self.temp.name) / "autoapply.db")
        service.CV_STORAGE_DIR = Path(self.temp.name) / "materialized"
        self.addCleanup(self._restore)
        db.initialize()
        heroku_entrypoint.ensure_cv_blob_column()

    def _restore(self) -> None:
        db.DB_PATH = self.old_db_path
        service.CV_STORAGE_DIR = self.old_cv_dir
        db.create_campaign = self.old_create
        db.get_campaign = self.old_get

    def _blob_for(self, campaign_id: str):
        connection = sqlite3.connect(db.DB_PATH)
        try:
            return connection.execute(
                "SELECT cv_blob FROM campaigns WHERE id=?", (campaign_id,)
            ).fetchone()[0]
        finally:
            connection.close()

    def test_existing_cv_is_embedded_and_materialized(self) -> None:
        source = Path(self.temp.name) / "legacy.pdf"
        payload = b"%PDF-1.4\nlegacy-cv\n%%EOF\n"
        source.write_bytes(payload)
        campaign, _ = self.old_create(
            candidate_name="Migration Test",
            candidate_email="migration@example.com",
            target_role="Operations Analyst",
            cv_path=str(source),
            cv_original_name="legacy.pdf",
            cv_sha256="test",
        )

        self.assertEqual(heroku_entrypoint.embed_existing_cvs(), 1)
        self.assertEqual(self._blob_for(campaign["id"]), payload)

        source.unlink()
        self.assertEqual(heroku_entrypoint.materialize_cvs(), 1)
        rebuilt = service.CV_STORAGE_DIR / "legacy.pdf"
        self.assertEqual(rebuilt.read_bytes(), payload)

    def test_new_campaign_wrapper_embeds_cv_without_exposing_blob(self) -> None:
        source = Path(self.temp.name) / "new.pdf"
        payload = b"%PDF-1.4\nnew-cv\n%%EOF\n"
        source.write_bytes(payload)

        db.create_campaign = heroku_entrypoint._portable_create_campaign
        campaign, _ = db.create_campaign(
            candidate_name="New Test",
            candidate_email="new@example.com",
            target_role="Engineer",
            cv_path=str(source),
            cv_original_name="new.pdf",
            cv_sha256="test",
        )
        self.assertEqual(self._blob_for(campaign["id"]), payload)


if __name__ == "__main__":
    unittest.main()

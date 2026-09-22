from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import migration_seed


class MigrationSeedTests(unittest.TestCase):
    def test_embeds_cv_and_uploads_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cv = root / "resume.pdf"
            payload = b"%PDF-1.4\nprivate-cv\n%%EOF\n"
            cv.write_bytes(payload)

            db_path = root / "autoapply.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "CREATE TABLE campaigns (id TEXT PRIMARY KEY, cv_path TEXT, updated_at REAL)"
                )
                connection.execute(
                    "INSERT INTO campaigns(id,cv_path,updated_at) VALUES(?,?,0)",
                    ("c1", str(cv)),
                )
                connection.commit()
            finally:
                connection.close()

            with patch("migration_seed.heroku_persistence.configured", return_value=True), patch(
                "migration_seed.heroku_persistence.snapshot", return_value=True
            ) as snapshot:
                result = migration_seed.seed_snapshot(db_path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["embedded_cv_count"], 1)
            snapshot.assert_called_once_with(db_path, force=True)

            connection = sqlite3.connect(db_path)
            try:
                row = connection.execute("SELECT cv_blob FROM campaigns WHERE id='c1'").fetchone()
            finally:
                connection.close()
            self.assertEqual(row[0], payload)


if __name__ == "__main__":
    unittest.main()

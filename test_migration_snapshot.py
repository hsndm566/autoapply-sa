from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import db
import migration_snapshot


class MigrationSnapshotTests(unittest.TestCase):
    def test_creates_consistent_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            old = db.DB_PATH
            try:
                db.DB_PATH = str(Path(temp) / "source.db")
                db.initialize()
                campaign, _ = db.create_campaign(
                    candidate_name="Snapshot Test",
                    candidate_email="snapshot@example.com",
                    target_role="Engineer",
                )
                out = Path(temp) / "copy.db"
                result = migration_snapshot.snapshot(out)
                self.assertTrue(result["ok"])
                self.assertGreater(result["bytes"], 0)
                connection = sqlite3.connect(out)
                try:
                    row = connection.execute(
                        "SELECT id FROM campaigns WHERE id=?", (campaign["id"],)
                    ).fetchone()
                finally:
                    connection.close()
                self.assertIsNotNone(row)
            finally:
                db.DB_PATH = old


if __name__ == "__main__":
    unittest.main()

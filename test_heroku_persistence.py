from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import heroku_persistence
from botocore.exceptions import ClientError


class FakeS3:
    def __init__(self):
        self.objects = {}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.objects[key] = Path(filename).read_bytes()

    def download_file(self, bucket, key, filename):
        Path(filename).write_bytes(self.objects[key])


class HerokuPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(
            os.environ,
            {
                "S3_HERO_DEV_ACCESS_KEY_ID": "test-access",
                "S3_HERO_DEV_SECRET_KEY_ID": "test-secret",
                "S3_HERO_DEV_BUCKET_NAME": "test-bucket",
                "S3_HERO_DEV_REGION_NAME": "us-east-1",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.s3 = FakeS3()
        self.client = patch("heroku_persistence.boto3.client", return_value=self.s3)
        self.client.start()
        self.addCleanup(self.client.stop)
        heroku_persistence._LAST_DIGEST = None

    def make_db(self, path: Path, value: str) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE state(value TEXT)")
            connection.execute("INSERT INTO state VALUES(?)", (value,))
            connection.commit()
        finally:
            connection.close()

    def read_value(self, path: Path) -> str:
        connection = sqlite3.connect(path)
        try:
            return connection.execute("SELECT value FROM state").fetchone()[0]
        finally:
            connection.close()

    def test_snapshot_and_restore_round_trip(self) -> None:
        source = Path(self.temp.name) / "source.db"
        restored = Path(self.temp.name) / "restored.db"
        self.make_db(source, "durable")

        self.assertTrue(heroku_persistence.snapshot(source, force=True))
        self.assertTrue(heroku_persistence.remote_exists())
        self.assertTrue(heroku_persistence.restore(restored))
        self.assertEqual(self.read_value(restored), "durable")

    def test_missing_remote_returns_false(self) -> None:
        target = Path(self.temp.name) / "missing.db"
        self.assertFalse(heroku_persistence.remote_exists())
        self.assertFalse(heroku_persistence.restore(target))
        self.assertFalse(target.exists())

    def test_unchanged_snapshot_is_not_uploaded_twice(self) -> None:
        source = Path(self.temp.name) / "source.db"
        self.make_db(source, "same")
        self.assertTrue(heroku_persistence.snapshot(source, force=True))
        self.assertFalse(heroku_persistence.snapshot(source))


if __name__ == "__main__":
    unittest.main()

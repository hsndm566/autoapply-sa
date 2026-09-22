from __future__ import annotations

import unittest
from unittest.mock import Mock

from ops import heroku_migrate


class HerokuMigrationControllerTests(unittest.TestCase):
    def test_safe_config_removes_platform_only_values(self) -> None:
        source = {
            "DATABASE_URL": "mysql://example",
            "CLERK_SECRET_KEY": "secret",
            "PORT": "10000",
            "RENDER_SERVICE_ID": "srv-example",
            "RENDER_GIT_COMMIT": "abc",
        }
        result = heroku_migrate._safe_config(source)
        self.assertEqual(result["DATABASE_URL"], "mysql://example")
        self.assertEqual(result["CLERK_SECRET_KEY"], "secret")
        self.assertNotIn("PORT", result)
        self.assertNotIn("RENDER_SERVICE_ID", result)
        self.assertNotIn("RENDER_GIT_COMMIT", result)

    def test_free_s3_plan_prefers_zero_cost_and_refuses_paid_only(self) -> None:
        client = heroku_migrate.Heroku("test-token")
        client.call = Mock(
            return_value=[
                {"name": "s3herodev:test", "price": {"cents": 0}},
                {"name": "s3herodev:paid", "price": {"cents": 500}},
            ]
        )
        self.assertEqual(client._free_s3_plan(), "s3herodev:test")

        client.call = Mock(return_value=[{"name": "s3herodev:paid", "price": {"cents": 500}}])
        with self.assertRaises(heroku_migrate.MigrationError):
            client._free_s3_plan()

    def test_render_env_parser_handles_nested_api_shape_without_logging_values(self) -> None:
        client = heroku_migrate.Render("test-token")
        client.call = Mock(
            return_value=[
                {"envVar": {"key": "DATABASE_URL", "value": "mysql://private"}},
                {"envVar": {"key": "CLERK_SECRET_KEY", "value": "private-clerk"}},
            ]
        )
        values = client.env("srv-test")
        self.assertEqual(values["DATABASE_URL"], "mysql://private")
        self.assertEqual(values["CLERK_SECRET_KEY"], "private-clerk")

    def test_required_portal_config_fails_closed_when_render_cannot_read_it(self) -> None:
        heroku = heroku_migrate.Heroku("test-token")
        heroku.patch_config = Mock()
        with self.assertRaises(heroku_migrate.MigrationError):
            heroku_migrate._copy_render_config(
                {"VITE_CLERK_PUBLISHABLE_KEY": "pk", "CLERK_SECRET_KEY": "sk"},
                heroku,
                "portal-app",
                {},
                required=heroku_migrate.PORTAL_REQUIRED,
            )
        heroku.patch_config.assert_not_called()


if __name__ == "__main__":
    unittest.main()

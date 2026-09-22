from __future__ import annotations

import unittest

from ops import northflank_inventory as inv


class NorthflankInventoryTests(unittest.TestCase):
    def test_repo_normalization(self) -> None:
        self.assertEqual(inv._normalize_repo("https://github.com/hsndm566/autoapply-sa.git"), "hsndm566/autoapply-sa")
        self.assertEqual(inv._normalize_repo("git@github.com:hsndm566/hsndm.tech2.git"), "hsndm566/hsndm.tech2")

    def test_public_endpoints_deduplicate_dns_and_custom_domains(self) -> None:
        ports = [
            {
                "public": True,
                "dns": "svc.code.run",
                "domains": [{"name": "api.hsndm.tech"}, "api.hsndm.tech"],
            },
            {"public": False, "dns": "private.code.run", "domains": []},
        ]
        self.assertEqual(
            inv._public_endpoints(ports),
            ["https://api.hsndm.tech", "https://svc.code.run"],
        )

    def test_volume_summary_only_returns_target_service(self) -> None:
        volumes = [
            {
                "id": "state",
                "name": "AutoApply state",
                "status": "BOUND",
                "spec": {"storageClassName": "ssd", "storageSize": 6144},
                "mounts": [{"containerMountPath": "/data/autoapply"}],
                "attachedObjects": [{"id": "api", "type": "service"}],
            },
            {
                "id": "other",
                "name": "Other",
                "attachedObjects": [{"id": "portal", "type": "service"}],
            },
        ]
        result = inv._volume_summary(volumes, "api")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["mount_paths"], ["/data/autoapply"])

    def test_inventory_never_returns_runtime_values(self) -> None:
        class Fake:
            def projects(self):
                return [{"id": "p1", "name": "AutoApply"}]

            def services(self, project_id):
                return [{"id": "api", "name": "API"}, {"id": "portal", "name": "Portal"}]

            def service(self, project_id, service_id):
                repo = "hsndm566/autoapply-sa" if service_id == "api" else "hsndm566/hsndm.tech2"
                return {
                    "id": service_id,
                    "name": service_id,
                    "serviceType": "combined",
                    "vcsData": {"projectUrl": f"https://github.com/{repo}", "projectBranch": "main"},
                }

            def ports(self, project_id, service_id):
                return [{"public": True, "dns": f"{service_id}.code.run", "domains": []}]

            def runtime_env_names(self, project_id, service_id):
                return ["DATABASE_URL", "PRIVATE_SECRET"], True

            def volumes(self, project_id):
                return []

            def addons(self, project_id):
                return []

            def addon(self, project_id, addon_id):
                raise AssertionError("unused")

        result = inv.inventory(Fake())
        serialized = str(result)
        self.assertIn("PRIVATE_SECRET", serialized)
        self.assertNotIn("super-secret-value", serialized)
        self.assertTrue(result["ready_for_migration_planning"])
        self.assertEqual(result["missing_roles"], [])


if __name__ == "__main__":
    unittest.main()

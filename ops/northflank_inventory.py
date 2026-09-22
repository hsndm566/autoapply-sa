#!/usr/bin/env python3
"""Read-only Northflank source inventory for the AutoApply SA Heroku migration.

The script discovers the real Northflank projects/services backing the two GitHub
repositories. It never prints runtime secret values. It inventories service IDs,
public endpoints, persistent volumes, environment variable names, and add-ons so
later migration phases operate on verified resources rather than guessed provider
state.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API = "https://api.northflank.com/v1"
TARGET_REPOS = {
    "python_backend": "hsndm566/autoapply-sa",
    "portal_backend": "hsndm566/hsndm.tech2",
}


class InventoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResourceRef:
    project_id: str
    project_name: str
    service_id: str
    service_name: str
    role: str


def _normalize_repo(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"^git\+", "", text)
    text = re.sub(r"^https?://github\.com/", "", text)
    text = re.sub(r"^git@github\.com:", "", text)
    return text.removesuffix(".git").strip("/")


def _safe_domain(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, dict):
        for key in ("name", "domain", "dns"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


class Northflank:
    def __init__(self, token: str):
        if not token:
            raise InventoryError("NORTHFLANK_API_TOKEN is missing")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "autoapply-northflank-inventory",
        }

    def call(self, path: str, *, accepted: tuple[int, ...] = (200,)) -> Any:
        req = urllib.request.Request(API + path, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                if int(response.status) not in accepted:
                    raise InventoryError(f"Northflank returned HTTP {response.status}")
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise InventoryError(f"Northflank API returned HTTP {exc.code} for {path}") from None
        except urllib.error.URLError as exc:
            raise InventoryError(f"Northflank API network error: {exc.reason}") from None

    def projects(self) -> list[dict[str, Any]]:
        payload = self.call("/projects?per_page=100")
        return list((payload.get("data") or {}).get("projects") or [])

    def services(self, project_id: str) -> list[dict[str, Any]]:
        payload = self.call(f"/projects/{urllib.parse.quote(project_id, safe='')}/services?per_page=100")
        return list((payload.get("data") or {}).get("services") or [])

    def service(self, project_id: str, service_id: str) -> dict[str, Any]:
        payload = self.call(
            f"/projects/{urllib.parse.quote(project_id, safe='')}/services/{urllib.parse.quote(service_id, safe='')}"
        )
        return dict(payload.get("data") or {})

    def ports(self, project_id: str, service_id: str) -> list[dict[str, Any]]:
        payload = self.call(
            f"/projects/{urllib.parse.quote(project_id, safe='')}/services/{urllib.parse.quote(service_id, safe='')}/ports"
        )
        return list((payload.get("data") or {}).get("ports") or [])

    def runtime_env_names(self, project_id: str, service_id: str) -> tuple[list[str], bool]:
        path = (
            f"/projects/{urllib.parse.quote(project_id, safe='')}/services/"
            f"{urllib.parse.quote(service_id, safe='')}/runtime-environment"
            "?show=all&replaceTemplatedValues=true"
        )
        try:
            payload = self.call(path)
        except InventoryError as exc:
            if "HTTP 401" in str(exc) or "HTTP 403" in str(exc):
                return [], False
            raise
        runtime = (payload.get("data") or {}).get("runtimeEnvironment") or {}
        return sorted(str(key) for key in runtime), True

    def addons(self, project_id: str) -> list[dict[str, Any]]:
        payload = self.call(f"/projects/{urllib.parse.quote(project_id, safe='')}/addons?per_page=100")
        return list((payload.get("data") or {}).get("addons") or [])

    def addon(self, project_id: str, addon_id: str) -> dict[str, Any]:
        payload = self.call(
            f"/projects/{urllib.parse.quote(project_id, safe='')}/addons/{urllib.parse.quote(addon_id, safe='')}"
        )
        return dict(payload.get("data") or {})

    def volumes(self, project_id: str) -> list[dict[str, Any]]:
        payload = self.call(f"/projects/{urllib.parse.quote(project_id, safe='')}/volumes?per_page=100")
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.get("volumes") or [])
        return []


def _service_repo(detail: dict[str, Any]) -> str:
    vcs = detail.get("vcsData") or {}
    if isinstance(vcs, dict):
        return _normalize_repo(vcs.get("projectUrl"))
    return ""


def _public_endpoints(ports: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for port in ports:
        if not port.get("public"):
            continue
        dns = _safe_domain(port.get("dns"))
        if dns:
            values.append(f"https://{dns}")
        for domain in port.get("domains") or []:
            name = _safe_domain(domain)
            if name:
                values.append(f"https://{name}")
    return sorted(dict.fromkeys(values))


def _volume_summary(volumes: list[dict[str, Any]], service_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for volume in volumes:
        attached = volume.get("attachedObjects") or []
        if not any(
            isinstance(item, dict)
            and str(item.get("id") or "") == service_id
            and str(item.get("type") or "") == "service"
            for item in attached
        ):
            continue
        spec = volume.get("spec") or {}
        mounts = volume.get("mounts") or []
        out.append(
            {
                "id": str(volume.get("id") or ""),
                "name": str(volume.get("name") or ""),
                "status": str(volume.get("status") or ""),
                "storage_class": str(spec.get("storageClassName") or ""),
                "storage_size": spec.get("storageSize"),
                "mount_paths": sorted(
                    {
                        str(m.get("containerMountPath") or "")
                        for m in mounts
                        if isinstance(m, dict) and m.get("containerMountPath")
                    }
                ),
            }
        )
    return out


def _addon_summary(detail: dict[str, Any]) -> dict[str, Any]:
    spec = detail.get("spec") or {}
    addon_type = (
        detail.get("type")
        or detail.get("addonType")
        or (spec.get("type") if isinstance(spec, dict) else None)
        or ""
    )
    return {
        "id": str(detail.get("id") or ""),
        "name": str(detail.get("name") or ""),
        "type": str(addon_type),
        "status": str(detail.get("status") or ""),
        "version": str(detail.get("version") or ""),
    }


def inventory(client: Northflank) -> dict[str, Any]:
    projects = client.projects()
    discovered: list[dict[str, Any]] = []
    target_projects: dict[str, dict[str, Any]] = {}

    for project in projects:
        project_id = str(project.get("id") or "")
        if not project_id:
            continue
        project_name = str(project.get("name") or "")
        volumes = client.volumes(project_id)
        for service in client.services(project_id):
            service_id = str(service.get("id") or "")
            if not service_id:
                continue
            detail = client.service(project_id, service_id)
            repo = _service_repo(detail)
            role = next((key for key, target in TARGET_REPOS.items() if repo == target), None)
            if not role:
                continue

            ports = client.ports(project_id, service_id)
            env_names, can_read_secrets = client.runtime_env_names(project_id, service_id)
            record = {
                "role": role,
                "project_id": project_id,
                "project_name": project_name,
                "service_id": service_id,
                "service_name": str(detail.get("name") or service.get("name") or ""),
                "service_type": str(detail.get("serviceType") or ""),
                "repo": repo,
                "branch": str((detail.get("vcsData") or {}).get("projectBranch") or ""),
                "public_endpoints": _public_endpoints(ports),
                "runtime_variable_names": env_names,
                "runtime_secret_read_access": can_read_secrets,
                "volumes": _volume_summary(volumes, service_id),
            }
            discovered.append(record)
            target_projects[project_id] = {
                "id": project_id,
                "name": project_name,
            }

    addon_records: list[dict[str, Any]] = []
    for project_id, project in target_projects.items():
        for addon in client.addons(project_id):
            addon_id = str(addon.get("id") or "")
            if not addon_id:
                continue
            detail = client.addon(project_id, addon_id)
            summary = _addon_summary(detail)
            summary["project_id"] = project_id
            summary["project_name"] = project["name"]
            addon_records.append(summary)

    roles = {item["role"] for item in discovered}
    missing = sorted(set(TARGET_REPOS) - roles)
    return {
        "provider": "northflank",
        "read_only": True,
        "projects_scanned": len(projects),
        "services": sorted(discovered, key=lambda item: item["role"]),
        "addons": sorted(addon_records, key=lambda item: (item["project_name"], item["name"])),
        "missing_roles": missing,
        "ready_for_migration_planning": not missing,
    }


def main() -> None:
    token = os.environ.get("NORTHFLANK_API_TOKEN", "").strip()
    result = inventory(Northflank(token))
    output_path = os.environ.get("NORTHFLANK_INVENTORY_PATH", "northflank-inventory.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["missing_roles"]:
        raise SystemExit(3)


if __name__ == "__main__":
    try:
        main()
    except InventoryError as exc:
        print(f"INVENTORY FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)

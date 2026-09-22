#!/usr/bin/env python3
"""Chat-controlled AutoApply SA migration from Render to Heroku.

This script is intended to run only inside GitHub Actions with HEROKU_API_KEY
and RENDER_API_KEY stored as encrypted repository secrets. Secret values are
never printed. Production DNS is deliberately out of scope.

Migration order:
1. Verify both provider credentials.
2. Ensure two Heroku staging apps exist.
3. Provision only a zero-cost S3 Hero plan for the Python backend.
4. Copy current Render runtime config to Heroku in memory.
5. Temporarily let the Render Python service seed the Heroku S3 snapshot.
6. Deploy exact GitHub main commits to Heroku.
7. Scale each web process to one Eco dyno.
8. Verify health, DB, auth, and fail-closed external execution.
9. Remove temporary migration credentials from Render and redeploy fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

HEROKU_API = "https://api.heroku.com"
RENDER_API = "https://api.render.com/v1"

PYTHON_RENDER_SERVICE = "srv-d9vm7ck9v7es73b6k78g"
PORTAL_RENDER_SERVICE = "srv-da12uke1egvs739s2jhg"
PYTHON_RENDER_URL = "https://autoapply-sa.onrender.com"

PYTHON_REPO = "hsndm566/autoapply-sa"
PORTAL_REPO = "hsndm566/hsndm.tech2"

S3_KEYS = (
    "S3_HERO_DEV_ACCESS_KEY_ID",
    "S3_HERO_DEV_SECRET_KEY_ID",
    "S3_HERO_DEV_BUCKET_NAME",
    "S3_HERO_DEV_REGION_NAME",
)

RENDER_TEMP_KEYS = (*S3_KEYS, "ALLOW_MIGRATION_SNAPSHOT", "MIGRATION_SNAPSHOT_TOKEN")

PLATFORM_ENV_PREFIXES = ("RENDER_",)
PLATFORM_ENV_KEYS = {
    "PORT",
    "RENDER",
    "IS_PULL_REQUEST",
    "RENDER_EXTERNAL_URL",
    "RENDER_SERVICE_ID",
    "RENDER_SERVICE_NAME",
    "RENDER_SERVICE_TYPE",
    "RENDER_INSTANCE_ID",
    "RENDER_GIT_BRANCH",
    "RENDER_GIT_COMMIT",
    "RENDER_GIT_REPO_SLUG",
}

PORTAL_REQUIRED = (
    "DATABASE_URL",
    "VITE_CLERK_PUBLISHABLE_KEY",
    "CLERK_SECRET_KEY",
)


class MigrationError(RuntimeError):
    pass


@dataclass
class HttpResult:
    status: int
    data: Any
    headers: dict[str, str]


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: Any = None,
    timeout: int = 60,
    accepted: tuple[int, ...] = (200, 201, 202, 204),
) -> HttpResult:
    request_headers = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else None
            status = int(response.status)
            if status not in accepted:
                raise MigrationError(f"unexpected HTTP status {status} from {urllib.parse.urlsplit(url).netloc}")
            return HttpResult(status, data, dict(response.headers.items()))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            detail = {"message": raw[:300]}
        error_id = detail.get("id") if isinstance(detail, dict) else None
        message = detail.get("message") if isinstance(detail, dict) else None
        safe = f"HTTP {exc.code}"
        if error_id:
            safe += f" {error_id}"
        if message and not any(word in str(message).lower() for word in ("token", "secret", "password", "credential")):
            safe += f": {str(message)[:240]}"
        raise MigrationError(f"{safe} from {urllib.parse.urlsplit(url).netloc}") from None
    except urllib.error.URLError as exc:
        raise MigrationError(f"network error contacting {urllib.parse.urlsplit(url).netloc}: {exc.reason}") from None


def _public_json(url: str) -> Any:
    return _request(
        "GET",
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "autoapply-heroku-migration"},
        accepted=(200,),
    ).data


def _github_main_sha(repo: str) -> str:
    data = _public_json(f"https://api.github.com/repos/{repo}/commits/main")
    sha = str(data.get("sha") or "").strip()
    if len(sha) < 20:
        raise MigrationError(f"unable to resolve main SHA for {repo}")
    return sha


def _safe_config(config: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in config.items()
        if key
        and value is not None
        and key not in PLATFORM_ENV_KEYS
        and not any(key.startswith(prefix) for prefix in PLATFORM_ENV_PREFIXES)
    }


class Heroku:
    def __init__(self, token: str):
        if not token:
            raise MigrationError("HEROKU_API_KEY is missing")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.heroku+json; version=3",
            "User-Agent": "autoapply-heroku-migration",
        }

    def call(self, method: str, path: str, payload: Any = None, accepted=(200, 201, 202, 204)) -> Any:
        return _request(method, HEROKU_API + path, headers=self.headers, payload=payload, accepted=accepted).data

    def account(self) -> dict[str, Any]:
        return self.call("GET", "/account", accepted=(200,))

    def app(self, name: str) -> dict[str, Any] | None:
        try:
            return self.call("GET", f"/apps/{urllib.parse.quote(name, safe='')}", accepted=(200,))
        except MigrationError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    def ensure_app(self, preferred_name: str, suffix: str) -> dict[str, Any]:
        existing = self.app(preferred_name)
        if existing:
            return existing
        candidates = (preferred_name, f"{preferred_name[:22].rstrip('-')}-{suffix[:6]}")
        last_error: Exception | None = None
        for name in candidates:
            existing = self.app(name)
            if existing:
                return existing
            try:
                app = self.call(
                    "POST",
                    "/apps",
                    {"name": name, "region": "us", "stack": "heroku-24"},
                    accepted=(201,),
                )
                print(f"Heroku app ready: {app['name']}")
                return app
            except MigrationError as exc:
                last_error = exc
                if "HTTP 422" not in str(exc):
                    raise
        raise MigrationError(f"unable to create a unique Heroku app: {last_error}")

    def config(self, app: str) -> dict[str, str]:
        data = self.call("GET", f"/apps/{app}/config-vars", accepted=(200,))
        return {str(k): str(v) for k, v in (data or {}).items() if v is not None}

    def patch_config(self, app: str, values: dict[str, str | None]) -> None:
        self.call("PATCH", f"/apps/{app}/config-vars", values, accepted=(200,))
        print(f"Heroku config updated for {app}: {', '.join(sorted(values))}")

    def addons(self, app: str) -> list[dict[str, Any]]:
        return list(self.call("GET", f"/apps/{app}/addons", accepted=(200,)) or [])

    def _free_s3_plan(self) -> str:
        plans = list(self.call("GET", "/addon-services/s3herodev/plans", accepted=(200,)) or [])
        candidates: list[dict[str, Any]] = []
        for plan in plans:
            name = str(plan.get("name") or "")
            prices = plan.get("price")
            zero = False
            if isinstance(prices, dict):
                cents = prices.get("cents")
                zero = cents == 0
            elif isinstance(prices, list):
                zero = any(isinstance(item, dict) and item.get("cents") == 0 for item in prices)
            if zero or "test" in name.lower() or "free" in name.lower():
                candidates.append(plan)
        if not candidates:
            raise MigrationError("no zero-cost S3 Hero plan is available; refusing to provision a paid add-on")
        plan = candidates[0]
        value = str(plan.get("name") or plan.get("id") or "").strip()
        if not value:
            raise MigrationError("zero-cost S3 Hero plan could not be identified")
        return value

    def ensure_free_s3(self, app: str) -> None:
        for addon in self.addons(app):
            service = addon.get("addon_service") or {}
            plan = addon.get("plan") or {}
            if str(service.get("name") or "") == "s3herodev" or str(plan.get("name") or "").startswith("s3herodev"):
                print(f"S3 Hero already attached to {app}")
                return
        plan = self._free_s3_plan()
        self.call("POST", f"/apps/{app}/addons", {"plan": plan}, accepted=(201,))
        print(f"Zero-cost S3 Hero provisioned for {app}")

    def wait_for_s3_config(self, app: str, timeout_seconds: int = 300) -> dict[str, str]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            config = self.config(app)
            if all(config.get(key) for key in S3_KEYS):
                return config
            time.sleep(5)
        raise MigrationError("S3 Hero did not expose all required config vars before timeout")

    def build(self, app: str, repo: str, sha: str, buildpack: str, timeout_seconds: int = 1200) -> dict[str, Any]:
        payload = {
            "source_blob": {
                "url": f"https://github.com/{repo}/archive/{sha}.tar.gz",
                "version": sha,
                "version_description": f"{repo}@{sha[:12]}",
            },
            "buildpacks": [{"name": buildpack}],
        }
        build = self.call("POST", f"/apps/{app}/builds", payload, accepted=(201,))
        build_id = str(build.get("id") or "")
        if not build_id:
            raise MigrationError(f"Heroku did not return a build id for {app}")
        print(f"Heroku build started for {app}: {sha[:12]}")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            build = self.call("GET", f"/apps/{app}/builds/{build_id}", accepted=(200,))
            status = str(build.get("status") or "")
            if status == "succeeded":
                print(f"Heroku build succeeded for {app}")
                return build
            if status == "failed":
                raise MigrationError(f"Heroku build failed for {app}")
            time.sleep(8)
        raise MigrationError(f"Heroku build timed out for {app}")

    def scale_eco(self, app: str) -> None:
        self.call(
            "PATCH",
            f"/apps/{app}/formation/web",
            {"quantity": 1, "dyno_size": {"name": "eco"}},
            accepted=(200,),
        )
        print(f"Heroku web formation set to 1 Eco dyno for {app}")


class Render:
    def __init__(self, token: str):
        if not token:
            raise MigrationError("RENDER_API_KEY is missing")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "autoapply-heroku-migration",
        }

    def call(self, method: str, path: str, payload: Any = None, accepted=(200, 201, 202, 204)) -> Any:
        return _request(method, RENDER_API + path, headers=self.headers, payload=payload, accepted=accepted).data

    def env(self, service_id: str) -> dict[str, str]:
        data = self.call("GET", f"/services/{service_id}/env-vars?limit=100", accepted=(200,))
        values: dict[str, str] = {}
        items = data if isinstance(data, list) else data.get("items", []) if isinstance(data, dict) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            env_var = item.get("envVar") if isinstance(item.get("envVar"), dict) else item
            key = env_var.get("key")
            value = env_var.get("value")
            if key and value is not None:
                values[str(key)] = str(value)
        return values

    def set_env(self, service_id: str, key: str, value: str) -> None:
        self.call(
            "PUT",
            f"/services/{service_id}/env-vars/{urllib.parse.quote(key, safe='')}",
            {"value": value},
            accepted=(200,),
        )

    def delete_env(self, service_id: str, key: str) -> None:
        try:
            self.call(
                "DELETE",
                f"/services/{service_id}/env-vars/{urllib.parse.quote(key, safe='')}",
                accepted=(204,),
            )
        except MigrationError as exc:
            if "HTTP 404" not in str(exc):
                raise

    def deploy(self, service_id: str, commit_sha: str | None = None, timeout_seconds: int = 1200) -> dict[str, Any]:
        payload: dict[str, Any] = {"clearCache": "do_not_clear"}
        if commit_sha:
            payload["commitId"] = commit_sha
        deploy = self.call("POST", f"/services/{service_id}/deploys", payload, accepted=(201, 202))
        deploy_id = str(deploy.get("id") or deploy.get("deploy", {}).get("id") or "")
        if not deploy_id:
            raise MigrationError("Render deploy did not return an id")
        print(f"Render deploy started for {service_id}")
        deadline = time.time() + timeout_seconds
        success = {"live"}
        failure = {
            "build_failed",
            "update_failed",
            "canceled",
            "cancelled",
            "deactivated",
            "pre_deploy_failed",
            "failed",
        }
        while time.time() < deadline:
            current = self.call("GET", f"/services/{service_id}/deploys/{deploy_id}", accepted=(200,))
            status = str(current.get("status") or "")
            if status in success:
                print(f"Render deploy live for {service_id}")
                return current
            if status in failure:
                raise MigrationError(f"Render deploy failed for {service_id}: {status}")
            time.sleep(8)
        raise MigrationError(f"Render deploy timed out for {service_id}")

    def restore_temp_env(self, service_id: str, original: dict[str, str], keys: tuple[str, ...]) -> None:
        for key in keys:
            if key in original:
                self.set_env(service_id, key, original[key])
            else:
                self.delete_env(service_id, key)


def _http_health(url: str, expected: tuple[int, ...] = (200,), headers: dict[str, str] | None = None) -> Any:
    result = _request("GET", url, headers=headers or {}, accepted=expected, timeout=90)
    return result.data


def _post_json(url: str, headers: dict[str, str]) -> Any:
    return _request("POST", url, headers=headers, payload={}, accepted=(200,), timeout=120).data


def _copy_render_config(
    render_values: dict[str, str],
    heroku: Heroku,
    app: str,
    overrides: dict[str, str],
    required: tuple[str, ...] = (),
) -> None:
    clean = _safe_config(render_values)
    missing = [key for key in required if not clean.get(key)]
    if missing:
        raise MigrationError(
            "Render API could not read required direct environment variables: " + ", ".join(missing)
            + ". They may be in a linked Render environment group."
        )
    clean.update(overrides)
    # Never forward migration-only credentials into Heroku.
    for key in RENDER_TEMP_KEYS:
        clean.pop(key, None)
    heroku.patch_config(app, clean)


def _seed_python_snapshot(
    *,
    render: Render,
    heroku: Heroku,
    api_app: str,
    python_sha: str,
    original_render_env: dict[str, str],
) -> None:
    s3_config = heroku.wait_for_s3_config(api_app)
    migration_token = secrets.token_urlsafe(48)
    temp_values = {key: s3_config[key] for key in S3_KEYS}
    temp_values.update(
        {
            "ALLOW_MIGRATION_SNAPSHOT": "true",
            "MIGRATION_SNAPSHOT_TOKEN": migration_token,
        }
    )

    cleanup_needed = False
    try:
        for key, value in temp_values.items():
            render.set_env(PYTHON_RENDER_SERVICE, key, value)
        cleanup_needed = True
        print("Temporary migration variables attached to Render Python service")
        render.deploy(PYTHON_RENDER_SERVICE, python_sha)

        result = _post_json(
            f"{PYTHON_RENDER_URL}/v1/admin/migration/snapshot",
            {"X-Migration-Token": migration_token, "Content-Type": "application/json"},
        )
        if not isinstance(result, dict) or result.get("snapshot_uploaded") is not True:
            raise MigrationError("Render snapshot endpoint did not confirm a durable upload")
        print(
            "Render state snapshot seeded to Heroku storage "
            f"(embedded CVs: {int(result.get('embedded_cv_count') or 0)}, "
            f"database bytes: {int(result.get('database_bytes') or 0)})"
        )
    finally:
        if cleanup_needed:
            try:
                render.restore_temp_env(PYTHON_RENDER_SERVICE, original_render_env, RENDER_TEMP_KEYS)
                render.deploy(PYTHON_RENDER_SERVICE, python_sha)
                print("Temporary migration variables removed from Render fallback")
            except Exception as cleanup_error:
                print(
                    "WARNING: Render migration-variable cleanup needs attention: "
                    f"{type(cleanup_error).__name__}",
                    file=sys.stderr,
                )


def migrate(request: dict[str, Any]) -> dict[str, Any]:
    heroku = Heroku(os.environ.get("HEROKU_API_KEY", "").strip())
    render = Render(os.environ.get("RENDER_API_KEY", "").strip())

    account = heroku.account()
    account_id = str(account.get("id") or "").replace("-", "")
    if len(account_id) < 6:
        raise MigrationError("Heroku account could not be verified")
    suffix = account_id[:6].lower()
    print("Heroku account verified")
    print("Render migration credential present")

    api_name = str(request.get("api_app_name") or f"autoapply-sa-api-{suffix}")[:30]
    portal_name = str(request.get("portal_app_name") or f"autoapply-sa-portal-{suffix}")[:30]

    api_app = heroku.ensure_app(api_name, suffix)
    portal_app = heroku.ensure_app(portal_name, suffix)

    heroku.ensure_free_s3(api_app["name"])
    heroku.wait_for_s3_config(api_app["name"])

    python_sha = _github_main_sha(PYTHON_REPO)
    portal_sha = _github_main_sha(PORTAL_REPO)
    print(f"Python source pinned: {python_sha[:12]}")
    print(f"Portal source pinned: {portal_sha[:12]}")

    python_render_env = render.env(PYTHON_RENDER_SERVICE)
    portal_render_env = render.env(PORTAL_RENDER_SERVICE)

    _copy_render_config(
        python_render_env,
        heroku,
        api_app["name"],
        {
            "DB_PATH": "/tmp/autoapply/autoapply.db",
            "CV_STORAGE_DIR": "/tmp/autoapply/cv",
            "CORS_ORIGIN": "https://hsndm.tech",
            "ALLOW_LEGACY_EXTERNAL_EXECUTION": "false",
            "ALLOW_GREENHOUSE_LIVE_SUBMISSION": "false",
            "EMAIL_OUTREACH_ENABLED": "false",
            "AUTOAPPLY_REQUIRE_REMOTE_SNAPSHOT": "false",
            "AUTOAPPLY_SNAPSHOT_INTERVAL_SECONDS": "3",
        },
    )

    _seed_python_snapshot(
        render=render,
        heroku=heroku,
        api_app=api_app["name"],
        python_sha=python_sha,
        original_render_env=python_render_env,
    )

    heroku.patch_config(api_app["name"], {"AUTOAPPLY_REQUIRE_REMOTE_SNAPSHOT": "true"})
    heroku.build(api_app["name"], PYTHON_REPO, python_sha, "heroku/python")
    heroku.scale_eco(api_app["name"])

    api_url = str(api_app.get("web_url") or f"https://{api_app['name']}.herokuapp.com/")
    api_health = _http_health(api_url.rstrip("/") + "/healthz")
    if not isinstance(api_health, dict) or api_health.get("ok") is not True:
        raise MigrationError("Heroku Python /healthz did not return ok=true")
    if api_health.get("external_execution_enabled") is not False:
        raise MigrationError("Heroku Python backend did not remain fail-closed")
    print("Heroku Python backend health verified")

    portal_overrides: dict[str, str] = {}
    if not portal_render_env.get("JWT_SECRET"):
        portal_overrides["JWT_SECRET"] = secrets.token_urlsafe(48)
        print("Portal JWT_SECRET was absent from direct Render vars; generated a new Heroku-only session secret")
    _copy_render_config(
        portal_render_env,
        heroku,
        portal_app["name"],
        portal_overrides,
        required=PORTAL_REQUIRED,
    )
    heroku.build(portal_app["name"], PORTAL_REPO, portal_sha, "heroku/nodejs")
    heroku.scale_eco(portal_app["name"])

    portal_url = str(portal_app.get("web_url") or f"https://{portal_app['name']}.herokuapp.com/")
    health = _http_health(portal_url.rstrip("/") + "/healthz")
    db_health = _http_health(portal_url.rstrip("/") + "/healthz/db")
    auth_health = _http_health(portal_url.rstrip("/") + "/healthz/auth")
    if not isinstance(health, dict) or health.get("status") != "healthy":
        raise MigrationError("Heroku portal /healthz did not report healthy")
    if not isinstance(db_health, dict) or db_health.get("status") != "healthy":
        raise MigrationError("Heroku portal database health failed")
    if not isinstance(auth_health, dict) or auth_health.get("status") != "healthy":
        raise MigrationError("Heroku portal Clerk readiness failed")
    print("Heroku portal health, database, and auth verified")

    return {
        "ok": True,
        "dns_changed": False,
        "production_traffic_changed": False,
        "python": {
            "app": api_app["name"],
            "url": api_url,
            "source_sha": python_sha,
            "health": "verified",
            "external_execution": "disabled",
        },
        "portal": {
            "app": portal_app["name"],
            "url": portal_url,
            "source_sha": portal_sha,
            "health": "verified",
            "database": "verified",
            "auth": "verified",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default="ops/heroku-deploy-request.json")
    args = parser.parse_args()

    request_path = args.request
    if os.path.exists(request_path):
        with open(request_path, "r", encoding="utf-8") as handle:
            request = json.load(handle)
    else:
        request = {}

    if request.get("execute") is not True:
        raise MigrationError("deployment request must contain execute=true")

    result = migrate(request)
    output = os.environ.get("GITHUB_OUTPUT")
    summary = json.dumps(result, separators=(",", ":"))
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"result={summary}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except MigrationError as exc:
        print(f"MIGRATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)

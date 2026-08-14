#!/usr/bin/env python3
"""Offline customer-journey dry runs for AutoApply SA.

This suite never opens a browser, sends email, submits an application, or calls an
external API. It exercises only deterministic profile and job-policy decisions.
"""
from __future__ import annotations

import json
from pathlib import Path
from config_loader import should_apply

ROOT = Path(__file__).resolve().parent

SCENARIOS = [
    {
        "id": "cust_01",
        "description": "KSA junior tech role on preferred ATS",
        "job": {"title": "Junior Software Engineer", "location": "Riyadh, Saudi Arabia", "platform": "greenhouse"},
        "expected": (True, "ok"),
    },
    {
        "id": "cust_02",
        "description": "KSA entry-level supply-chain role",
        "job": {"title": "Supply Chain Coordinator", "location": "Jeddah, KSA", "platform": "naukrigulf"},
        "expected": (True, "ok"),
    },
    {
        "id": "cust_03",
        "description": "KSA associate compliance role",
        "job": {"title": "Compliance Specialist", "location": "Dammam, Saudi Arabia", "platform": "ashby"},
        "expected": (True, "ok"),
    },
    {
        "id": "cust_04",
        "description": "Senior title must be rejected",
        "job": {"title": "Senior Process Improvement Engineer", "location": "Jubail, Saudi Arabia", "platform": "greenhouse"},
        "expected": (False, "senior_role"),
    },
    {
        "id": "cust_05",
        "description": "Manager title must be rejected",
        "job": {"title": "Operations Manager", "location": "Khobar, Saudi Arabia", "platform": "direct_sa"},
        "expected": (False, "senior_role"),
    },
    {
        "id": "cust_06",
        "description": "Outside-KSA location must be rejected",
        "job": {"title": "Junior Operations Analyst", "location": "Dubai, UAE", "platform": "direct_sa"},
        "expected": (False, "outside_ksa"),
    },
    {
        "id": "cust_07",
        "description": "Global remote must be rejected when no KSA location is stated",
        "job": {"title": "Graduate Data Analyst", "location": "Remote - Worldwide", "platform": "ashby"},
        "expected": (False, "outside_ksa"),
    },
    {
        "id": "cust_08",
        "description": "Bayt must be skipped",
        "job": {"title": "Industrial Engineering Intern", "location": "Yanbu, Saudi Arabia", "platform": "Bayt.com"},
        "expected": (False, "skipped_platform"),
    },
    {
        "id": "cust_09",
        "description": "Indeed must be skipped",
        "job": {"title": "Entry Level Quality Inspector", "location": "Riyadh, Saudi Arabia", "platform": "Indeed"},
        "expected": (False, "skipped_platform"),
    },
    {
        "id": "cust_10",
        "description": "Unknown platform must be held rather than implicitly approved",
        "job": {"title": "Business Operations Associate", "location": "Jeddah, Saudi Arabia", "platform": "unknown_portal"},
        "expected": (False, "unknown_platform"),
    },
    {
        "id": "cust_11",
        "description": "Malformed location must fail closed",
        "job": {"title": "Governance Assistant", "location": None, "platform": "direct_sa"},
        "expected": (False, "invalid_job_fields"),
    },
    {
        "id": "cust_12",
        "description": "Common misspelling should not silently evade geography checks",
        "job": {"title": "Logistics Coordinator", "location": "Jedda, Saudi Arabia", "platform": "direct_sa"},
        "expected": (True, "ok"),
    },
    {
        "id": "cust_13",
        "description": "Workday non-KSA flag must require review",
        "job": {"title": "Junior Process Engineer", "location": "Riyadh, Saudi Arabia", "platform": "Workday (non-KSA companies)"},
        "expected": (False, "manual_review_platform"),
    },
    {
        "id": "cust_14",
        "description": "Missing title must fail closed",
        "job": {"title": "", "location": "Riyadh, Saudi Arabia", "platform": "direct_sa"},
        "expected": (False, "invalid_job_fields"),
    },
]


def run() -> dict[str, object]:
    results = []
    for scenario in SCENARIOS:
        job = scenario["job"]
        expected = scenario["expected"]
        try:
            actual = should_apply(job.get("title"), job.get("location"), job.get("platform"))
            passed = tuple(actual) == tuple(expected)
            error = None
        except Exception as exc:  # The dry run intentionally records crashes as faults.
            actual = None
            passed = False
            error = f"{type(exc).__name__}: {exc}"
        results.append({
            "id": scenario["id"],
            "description": scenario["description"],
            "job": job,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "error": error,
        })

    report = {
        "mode": "offline_dry_run",
        "external_actions": False,
        "scenario_count": len(results),
        "passed": sum(1 for row in results if row["passed"]),
        "failed": sum(1 for row in results if not row["passed"]),
        "results": results,
    }
    output = ROOT / "dry_run_report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()

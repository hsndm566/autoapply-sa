#!/usr/bin/env python3
"""Compatibility entry point for safe autonomous maintenance.

The previous version loaded a JSON file and submitted raw jobs directly to
Greenhouse, Ashby, and Lever. That path is intentionally retired. Discovery and
path verification now flow through the campaign worker; drafting and submission
require the human review gate.
"""
from __future__ import annotations

import json

import campaign_worker


def run_loop() -> dict[str, object]:
    result = campaign_worker.run_maintenance_cycle(discover_campaigns=True)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


if __name__ == "__main__":
    run_loop()

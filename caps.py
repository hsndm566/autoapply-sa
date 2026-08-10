#!/usr/bin/env python3
"""
caps.py — Hard action ceilings. No ceiling = a bug becomes a disaster.
Checked before every submit; honors global RUN_ENABLED kill switch.
"""
import db

def can_proceed(action_type="submit", client_id="system"):
    """Returns (allowed: bool, reason: str)."""
    if db.kill_switch_on():
        return False, "KILL_SWITCH_ON"
    per_hour, per_run = db.budget_for(action_type)
    if db.action_count_window(action_type, 3600) >= per_hour:
        return False, f"RATE_HOURLY:{db.action_count_window(action_type,3600)}/{per_hour}"
    if db.action_count_run(action_type) >= per_run:
        return False, f"RUN_CAP:{db.action_count_run(action_type)}/{per_run}"
    return True, "ok"

def enforce(action_type="submit", client_id="system"):
    ok, reason = can_proceed(action_type, client_id)
    if not ok:
        raise RuntimeError(f"CAP_BLOCKED:{reason}")
    return True

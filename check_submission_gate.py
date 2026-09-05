#!/usr/bin/env python3
"""Static CI check for known employer-facing approval bypasses.

This is intentionally narrow. It protects the current submission boundaries and
forces reviewers to update the allowlist when a new live sender is introduced.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORTAL_FILES = {
    "greenhouse_submit.py": "submit_greenhouse",
    "lever_submit.py": "submit_lever",
    "ashby_submit.py": "submit_ashby",
    "browserbase_submit.py": "submit_application",
    "local_submit.py": "submit_application",
}


def text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def fail(message: str) -> None:
    raise SystemExit(f"SUBMISSION GATE CHECK FAILED: {message}")


def main() -> None:
    for filename, function_name in PORTAL_FILES.items():
        source = text(filename)
        pattern = rf"@requires_approval\s*\n(?:@[^\n]+\n)*def\s+{re.escape(function_name)}\s*\("
        if not re.search(pattern, source):
            fail(f"{filename}:{function_name} is not protected by @requires_approval")
        if "captcha_solver" in source:
            fail(f"{filename} still references captcha_solver")
        if "mark_submitted(" not in source:
            fail(f"{filename} does not produce verified submission evidence")

    email = text("email_dispatcher.py")
    if "guard(review_record)" not in email:
        fail("email_dispatcher.dispatch_one does not recheck the human approval record")
    if '"human_approval_record"' not in email:
        fail("email outbox does not persist the human approval record")
    if "mark_submitted(" not in email:
        fail("email dispatcher does not validate provider evidence through mark_submitted")

    loop = text("autonomous_loop.py")
    forbidden = ("submit_greenhouse(", "submit_lever(", "submit_ashby(")
    for token in forbidden:
        if token in loop:
            fail(f"autonomous_loop.py still contains direct legacy submission call {token}")
    if "approve_draft(" in loop:
        fail("autonomous_loop.py is not allowed to approve its own drafts")

    for path in ROOT.glob("*submit*.py"):
        if path.name == "check_submission_gate.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "import captcha_solver" in source or "from captcha_solver" in source:
            fail(f"{path.name} imports CAPTCHA bypass code")

    print("submission gate static check: PASS")


if __name__ == "__main__":
    main()

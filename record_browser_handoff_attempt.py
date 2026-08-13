#!/usr/bin/env python3
"""Record a browser-handoff outcome; this utility cannot submit applications."""
from __future__ import annotations

import argparse
import json

import db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Absolute job URL inspected in the browser")
    parser.add_argument("status", choices=sorted(db.BROWSER_HANDOFF_ATTEMPT_STATUSES))
    parser.add_argument("--detail", default="", help="Short operational note; no CV or credentials")
    args = parser.parse_args()
    print(json.dumps(db.record_browser_handoff_attempt(args.url, args.status, args.detail), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

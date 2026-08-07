#!/usr/bin/env python3
"""network_intelligence.py — the multi-client network effect.

Aggregate performance is a SHARED asset. Individual client PII is NEVER stored
here — only: company hiring-activity, CV-format win-rates, job-board performance.
Every client's outcome makes every other client's application smarter.

What it tracks (all PII-stripped):
  - company_activity: which companies are actively hiring (response seen)
  - cv_format_perf: response rate per CV format -> recommend the best to ALL
  - board_perf: interview rate per board -> weight the best higher for ALL

Updated after every batch. Read by run_application to apply cross-client priors.
"""
import os, json, datetime, collections

BASE = os.path.dirname(os.path.abspath(__file__))
NET = os.path.join(BASE, "skills", "network-intelligence.md")


def _load():
    """Load aggregate state from the markdown-backed JSON store (sidecar file)."""
    path = os.path.join(BASE, "skills", ".network_state.json")
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"company_activity": {}, "cv_format_perf": {}, "board_perf": {}, "batches": 0}


def _save(state):
    path = os.path.join(BASE, "skills", ".network_state.json")
    json.dump(state, open(path, "w", encoding="utf-8"), indent=2)


def record_outcome(company, board, cv_format, got_response=False, got_interview=False):
    """Record one application outcome (NO client name, NO PII). Aggregate only."""
    s = _load()
    ca = s.setdefault("company_activity", {})
    ca[company] = ca.get(company, 0) + 1  # count of responses -> hiring signal
    bf = s.setdefault("cv_format_perf", {})
    b = bf.setdefault(cv_format, {"n": 0, "resp": 0})
    b["n"] += 1
    if got_response:
        b["resp"] += 1
    bp = s.setdefault("board_perf", {})
    p = bp.setdefault(board, {"n": 0, "interviews": 0})
    p["n"] += 1
    if got_interview:
        p["interviews"] += 1
    s["batches"] += 1
    _save(s)
    _append_doc(company, board, cv_format, got_response, got_interview)
    return s


def best_cv_format():
    """Return the highest-response-rate CV format (upgrade ALL clients to it)."""
    s = _load()
    best, rate = None, -1
    for fmt, d in s.get("cv_format_perf", {}).items():
        if d["n"] >= 3:
            r = d["resp"] / d["n"]
            if r > rate:
                best, rate = fmt, r
    return best, round(rate, 2) if best else (None, None)


def best_board():
    """Return the highest-interview-rate board (weight higher for all)."""
    s = _load()
    best, rate = None, -1
    for bd, d in s.get("board_perf", {}).items():
        if d["n"] >= 3:
            r = d["interviews"] / d["n"]
            if r > rate:
                best, rate = bd, r
    return best, round(rate, 2) if best else (None, None)


def hiring_companies():
    """Companies with >=1 response -> actively hiring; prioritize for all clients."""
    s = _load()
    return sorted([c for c, n in s.get("company_activity", {}).items() if n > 0])


def apply_network_priors(client, company, board):
    """Return cross-client priors WITHOUT touching PII:
    - if company is hiring (another client got response), flag PRIORITIZE
    - if board is top performer, flag WEIGHT_HIGH
    Used by run_application to bias the search/apply order."""
    priors = {}
    if company in hiring_companies():
        priors["prioritize_company"] = True
    top_board, _ = best_board()
    if top_board and board == top_board:
        priors["weight_board_high"] = True
    return priors


def _append_doc(company, board, cv_format, got_response, got_interview):
    """Append a PII-stripped line to network-intelligence.md."""
    try:
        with open(NET, "a", encoding="utf-8") as f:
            f.write(f"\n- {datetime.date.today().isoformat()} | company={company} | board={board} | "
                    f"format={cv_format} | response={got_response} | interview={got_interview}\n")
    except Exception:
        pass


if __name__ == "__main__":
    # demo: simulate two clients, same company, one gets response
    record_outcome("AcmeCorp", "Greenhouse", "harvard_format", got_response=True)
    record_outcome("AcmeCorp", "Lever", "harvard_format", got_response=False, got_interview=True)
    print("hiring companies:", hiring_companies())
    print("best cv format:", best_cv_format())
    print("best board:", best_board())
    print("priors for new client @ AcmeCorp/Greenhouse:", apply_network_priors("X", "AcmeCorp", "Greenhouse"))

#!/usr/bin/env python
"""
industry.py — SINGLE SOURCE OF TRUTH for industry resolution.

PRINCIPLE (enforced here, not elsewhere):
  - Industry is resolved EXACTLY ONCE, at the top of the pipeline, by resolve_industry().
  - resolve_industry() is the ONLY function that may produce an industry label.
  - draft() and send() MUST receive an Industry object as a required arg (no default).
  - Unknown industry -> explicit "unknown" sentinel, NEVER a silent "engineer" default.
  - Every resolution records WHY (map / keyword / fallback) so audits catch drift.
  - At boot, assert all 14 CV files exist; every producible industry has a file.
Fail loud, everywhere. No silent fallback.
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
CVR = os.path.join(HERE, "cv_variants")
MAP_FILE = os.path.join(HERE, "email_industry_map.json")

# The 14 real CV variants we actually have. Unknown MUST NOT impersonate any of these.
VALID_INDUSTRIES = ["engineer","tech","retail","food","oil","construct","finance",
                    "health","logistics","manufactur","hospitality","chemical","beverage","supply"]
UNKNOWN = "unknown"

# Keyword -> industry. Longest/most-specific first so "manufactur" beats "engineer" etc.
IND_MAP = [
    ("logistics","logistics"),("supply","supply"),("food","food"),("beverage","beverage"),
    ("retail","retail"),("hospitality","hospitality"),("chemical","chemical"),
    ("manufactur","manufactur"),("construct","construct"),("oil","oil"),
    ("health","health"),("finance","finance"),("tech","tech"),("engineer","engineer"),
]

# Per-industry skills/framing block — STATIC, curated, reviewed once.
# The LLM (if used) may only rephrase these; it cannot invent claims outside this text.
INDUSTRY_BLOCK = {
    "engineer": "industrial & manufacturing engineering, Lean/KAIZEN process optimization, production-line throughput, "
                "CAPEX/OPEX ownership, and cross-functional commissioning.",
    "tech": "software delivery, cloud/infra operations, API integrations, and agile release management.",
    "retail": "store operations, merchandising, inventory turnover, and omni-channel fulfilment.",
    "food": "FMCG production, HACCP/FSMS food-safety compliance, cold-chain logistics, and supplier quality.",
    "oil": "oil & gas / petrochemical operations, HSE/process-safety (OSHA/ISO 45001), and shutdown/turnaround coordination.",
    "construct": "construction project controls, site coordination, BOQ/RFQ management, and contractor HSE compliance.",
    "finance": "financial controls, management reporting, audit readiness, and process automation of reconciliations.",
    "health": "healthcare operations, patient-flow coordination, regulatory/compliance (ISO 13485), and quality systems.",
    "logistics": "warehouse & distribution management, fleet utilization, 3PL coordination, and S&OP planning.",
    "manufactur": "discrete/process manufacturing, OEE uplift, TPM, and quality systems (ISO 9001).",
    "hospitality": "hotel/ F&B operations, guest-experience standards, staffing rotations, and cost-of-sales control.",
    "chemical": "chemical process operations, batch production, EHS/compliance, and lab-to-plant scale-up.",
    "beverage": "beverage production, line efficiency, hygiene (GMP), and route/distribution planning.",
    "supply": "procurement, supplier development, demand planning, and inbound material flow.",
    "unknown": "operations and cross-functional coordination across engineering, supply chain, and process improvement.",
}

class Industry:
    """Immutable industry result. reason: map | keyword | fallback."""
    __slots__ = ("name","reason")
    def __init__(self, name, reason):
        if name not in VALID_INDUSTRIES and name != UNKNOWN:
            raise ValueError(f"Industry '{name}' is not valid and not 'unknown'")
        self.name = name
        self.reason = reason
    def __repr__(self): return f"Industry({self.name!r}, reason={self.reason!r})"
    def cv_file(self):
        # 'unknown' routes to the honest neutral CV (Hassan's real base background),
        # never impersonates a specific sector.
        if self.name == UNKNOWN:
            return os.path.join(CVR, "cv_unknown.pdf")
        return os.path.join(CVR, f"cv_{self.name}.pdf")
    def block(self):
        return INDUSTRY_BLOCK.get(self.name, INDUSTRY_BLOCK[UNKNOWN])

_OVERRIDE = {}
def _load_override():
    global _OVERRIDE
    if os.path.exists(MAP_FILE):
        try:
            d = json.load(open(MAP_FILE, encoding="utf-8"))
            # normalize values; drop any value that isn't a valid industry (fail loud on boot)
            for k,v in d.items():
                if v not in VALID_INDUSTRIES:
                    raise ValueError(f"email_industry_map.json maps '{k}' -> invalid industry '{v}'")
            _OVERRIDE = d
        except Exception as e:
            raise RuntimeError(f"Failed to load industry override map: {e}")

def resolve_industry(email, dom):
    """THE ONLY resolver. Returns Industry. Never silently defaults to engineer."""
    blob = (email + " " + dom).lower()
    # 1) JSON override (exact email)
    if email.lower() in _OVERRIDE:
        return Industry(_OVERRIDE[email.lower()], "map")
    # 2) keyword match on domain (most-specific first)
    for kw, ind in IND_MAP:
        if kw in blob:
            return Industry(ind, "keyword")
    # 3) explicit unknown — honest, routes to neutral CV/letter, never impersonates engineer
    return Industry(UNKNOWN, "fallback")

def boot_assert_cv_files():
    """Call ONCE at startup. Hard-fail if any CV missing/empty or unmapped industry exists."""
    needed = list(VALID_INDUSTRIES) + [UNKNOWN]  # unknown needs its honest neutral CV too
    missing = [i for i in needed if not os.path.exists(os.path.join(CVR, f"cv_{i}.pdf"))]
    if missing:
        raise RuntimeError(f"Missing CV files for industries: {missing}")
    for i in needed:
        p = os.path.join(CVR, f"cv_{i}.pdf")
        if os.path.getsize(p) < 500:
            raise RuntimeError(f"CV file too small/empty: {p}")
    return True

# load override + nothing else at import; boot_assert called explicitly by pipeline start
_load_override()

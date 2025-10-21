import re
from typing import Literal

# ---------
# Intent detection
# ---------

# Strong signals that the user wants a PLAN (but we still run UAA-only right now)
PLAN_PATTERNS = [
    r"\b(let'?s|help me)\s+plan\b",
    r"\broadmap\b",
    r"\baction\s+plan\b",
    r"\b3[-\s]?month(s)?\b",
    r"\b(\d+)\s*month\s*plan\b",
    r"\bmonth\s*1\b", r"\bmonth\s*2\b", r"\bmonth\s*3\b",
    r"\bweek\s*1\b", r"\bweek\s*2\b", r"\bweek\s*3\b",
    r"\bquarter(ly)?\b",
    r"\bschedule\b",
    r"\btimeline\b",
]

# Generic informational / learning asks (default)
LEARN_PATTERNS = [
    r"\b(explain|what is|how does|help me understand|overview|guide)\b",
    r"\b(best practices?|tips|advice)\b",
    r"\bcompare|versus|vs\.\b",
]

def _match_any(text: str, patterns: list[str]) -> bool:
    t = text or ""
    for p in patterns:
        if re.search(p, t, flags=re.IGNORECASE):
            return True
    return False

def detect_intent(text: str) -> Literal["plan", "learn"]:
    """Return 'plan' if the phrasing indicates planning; otherwise 'learn'."""
    if _match_any(text, PLAN_PATTERNS):
        return "plan"
    return "learn"


# ---------
# Affect detection (very lightweight heuristic; optional)
# ---------

AFFECT_PATTERNS = {
    "urgent": [r"\burgent\b", r"\basap\b", r"\bnow\b", r"\bimmediately\b", r"\bdeadline\b"],
    "frustrated": [r"\bfrustrat(ed|ing)\b", r"\bangry\b", r"\bupset\b", r"\bannoy(ed|ing)\b"],
    "positive": [r"\bthanks\b", r"\bappreciate\b", r"\bawesome\b", r"\bgreat\b", r"\bperfect\b"],
}

def detect_affect(text: str) -> str:
    t = text or ""
    for label, pats in AFFECT_PATTERNS.items():
        for p in pats:
            if re.search(p, t, flags=re.IGNORECASE):
                return label
    return "neutral"

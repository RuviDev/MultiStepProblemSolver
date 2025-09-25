from typing import Dict, Any, List
from datetime import datetime

def _now_iso() -> str:
    try:
        return datetime.utcnow().isoformat() + "Z"
    except Exception:
        return ""

def get_policy(env: Dict[str,Any]) -> Dict[str,Any]:
    defaults = {
        "ask_micro_questions": True,
        "micro_question_budget": 2,
        "min_confidence_to_skip": 0.70,
        "repeat_interval_turns": 3,
        "max_emits_per_problem": 3,
        "prefer_inline_block": True,
        "suppress_if_answerability_full": True,
        "respect_user_no_questions": True
    }
    p = ((env or {}).get("thread_policy") or {}).get("survey", {})
    return {**defaults, **p}

def current_turn_index(state: Dict[str,Any]) -> int:
    if "turn_index" in state and isinstance(state["turn_index"], int):
        return state["turn_index"]
    return len((state or {}).get("turn_records") or [])

def filter_candidates(policy: Dict[str,Any],
                      pr: Dict[str,Any],
                      candidates: List[str],
                      turn_idx: int) -> List[str]:
    if not policy.get("ask_micro_questions", True):
        return []
    if (pr or {}).get("no_more_questions") and policy.get("respect_user_no_questions", True):
        return []

    asked_map = (pr or {}).get("asked_insights") or {}
    answered = set((pr or {}).get("answered_insights") or [])
    min_conf = float(policy.get("min_confidence_to_skip", 0.7))
    repeat_gap = int(policy.get("repeat_interval_turns", 3))
    budget = int(policy.get("micro_question_budget", 2))

    def _has_conf(k: str) -> bool:
        v = (pr or {}).get("insights", {}).get(k)
        return bool(v and v.get("value") not in (None, "") and v.get("confidence", 0) >= min_conf)

    filtered = []
    for k in candidates:
        if k in answered or _has_conf(k):
            continue
        last_asked = int(asked_map.get(k, -10**9))
        if turn_idx - last_asked < repeat_gap:
            continue
        filtered.append(k)

    return filtered[:budget]

def record_asked(pr: Dict[str,Any], keys: List[str], turn_idx: int) -> None:
    if not keys:
        return
    pr.setdefault("asked_insights", {})
    for k in keys:
        pr["asked_insights"][k] = turn_idx
    pr["asked_count"] = int(pr.get("asked_count", 0)) + 1
    pr["last_updated"] = _now_iso()

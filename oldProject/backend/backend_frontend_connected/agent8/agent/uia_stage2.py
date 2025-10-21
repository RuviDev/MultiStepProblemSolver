from typing import Dict, Any, List
from agent.survey_policy import get_policy, current_turn_index, filter_candidates

def _by_id(items: List[Dict[str,Any]], key: str="id") -> Dict[str,Dict[str,Any]]:
    return { it.get(key): it for it in (items or []) if it.get(key) }

def _needs_for_painpoint(gpp: Dict[str,Any], pp_id: str) -> List[str]:
    by = _by_id((gpp or {}).get("pain_points") or [])
    return (by.get(pp_id) or {}).get("requires_insights") or []

def _mcq_from_git(git: Dict[str,Any], key: str) -> Dict[str,Any]:
    for it in (git or {}).get("insights", []):
        if it.get("key") == key:
            return {
                "key": key, "type": it.get("type","text"),
                "label": it.get("label", key), "options": it.get("options") or []
            }
    return {"key": key, "type": "text", "label": key}

def readiness_check(env: Dict[str,Any],
                    thread_state: Dict[str,Any],
                    step2: Dict[str,Any],
                    step5: Dict[str,Any]) -> Dict[str,Any]:
    catalogs = env.get("catalog_data",{}) or {}
    gpp = catalogs.get("gpp_taxonomy",{}) or {}
    git = catalogs.get("insight_catalog",{}) or {}

    prs = thread_state.get("problem_records") or []
    pr = prs[-1] if prs else {}
    insights = pr.get("insights", {})

    pc = (step2 or {}).get("problem_context", {}) or {}
    pain_points = pc.get("pain_points", []) or []

    seen = set(); required = []
    for pid in pain_points:
        for k in _needs_for_painpoint(gpp, pid):
            if k not in seen:
                seen.add(k); required.append(k)

    def _is_missing(k: str) -> bool:
        v = insights.get(k)
        return not v or (v.get('value') in (None,'')) or (v.get('confidence',0) < 0.5)
    candidates = [k for k in required if _is_missing(k)]

    policy = get_policy(env)
    turn_idx = current_turn_index(thread_state)
    intent = (thread_state or {}).get('last_intent','learn')
    should_ask = (intent in ('plan','decide','execute'))
    clean_keys = filter_candidates(policy, pr, candidates, turn_idx) if should_ask else []

    if not required or not clean_keys:
        return {"ok": True, "ready_for_planning": True, "missing": [], "survey": {}}

    fields = {k: _mcq_from_git(git, k) for k in clean_keys}
    return {"ok": True, "ready_for_planning": False, "missing": clean_keys,
            "survey": {"required_keys": clean_keys, "fields": fields}}

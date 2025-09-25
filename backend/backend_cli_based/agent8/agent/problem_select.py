
from typing import Dict, Any, List, Set
from datetime import datetime

def _now_iso(): return datetime.utcnow().isoformat()+"Z"
def _gen_problem_id(role_id: str): 
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"P-{(role_id or 'unknown').replace('-','_')}-{ts}"
def _union_unique(a, b):
    s = set(a or []); [s.add(x) for x in (b or [])]
    return list(s)

def _required_insights_for(pain_points: List[str], gpp_taxonomy: Dict[str, Any]) -> List[str]:
    req: Set[str] = set()
    by_id = {p["id"]: p for p in gpp_taxonomy.get("pain_points", [])}
    for pid in (pain_points or []):
        pp = by_id.get(pid)
        if not pp: continue
        for rid in pp.get("requires_insights", []):
            req.add(rid)
    return sorted(list(req))

def problem_selection_and_binding(env, thread_state, step2):
    decisions = step2.get("decisions", {}); ctx = step2.get("problem_context", {})
    if decisions.get("out_of_scope"):
        return {"ok": False, "status": "out_of_scope",
                "message": "This seems outside the current boundary. Please ask about junior tech roles and their pain points."}
    if decisions.get("category_conflict") and env.get("thread_policy",{}).get("one_category_per_thread", True):
        return {"ok": False, "status": "category_conflict",
                "message": "Different role than this thread. Start a new chat for the new role."}
    role_id = ctx.get("employment_category"); pp_list = ctx.get("pain_points", [])
    mapping_confidence = ctx.get("mapping_confidence", 0.0); ambiguous = bool(ctx.get("ambiguous", False))
    if not role_id:
        return {"ok": False, "status": "needs_role",
                "message": "I couldn’t detect the role. Please state the target role (e.g., Junior Data Analyst)."}
    existing = None
    for pr in thread_state.get("problem_records", []):
        if pr.get("employment_category") == role_id:
            existing = pr; break
    gpp = env.get("catalog_data",{}).get("gpp_taxonomy",{})
    required_insights = _required_insights_for(pp_list, gpp)
    if existing:
        existing["pain_points"] = _union_unique(existing.get("pain_points", []), pp_list)
        existing["mapping_confidence"] = round((existing.get("mapping_confidence",0.0)+mapping_confidence)/2.0, 3)
        existing["ambiguous"] = bool(existing.get("ambiguous", False) or ambiguous)
        existing["turns"] = int(existing.get("turns",0)) + 1
        existing["queued_categories"] = _union_unique(existing.get("queued_categories", []), ctx.get("queued_categories", []))
        existing["last_updated"] = _now_iso()
        status = "updated"; problem_id = existing["problem_id"]
    else:
        problem_id = _gen_problem_id(role_id)
        pr = {
            "problem_id": problem_id,
            "employment_category": role_id,
            "pain_points": pp_list,
            "pcc_snapshot": env.get("pcc_defaults", {}),
            "mapping_confidence": mapping_confidence,
            "ambiguous": ambiguous,
            "turns": 1,
            "evidence_used": False,
            "queued_categories": ctx.get("queued_categories", []),
            "insights": {},
            "last_updated": _now_iso()
        }
        thread_state.setdefault("problem_records", []).append(pr)
        status = "created"
    binding = {"status": status, "problem_id": problem_id, "employment_category": role_id,
               "pain_points": pp_list, "mapping_confidence": mapping_confidence,
               "ambiguous": ambiguous, "required_insights": required_insights}
    return {"ok": True, "binding": binding}

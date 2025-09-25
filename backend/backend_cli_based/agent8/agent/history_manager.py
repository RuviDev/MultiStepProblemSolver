
from typing import Dict, Any, List
from datetime import datetime

def _now_iso(): return datetime.utcnow().isoformat()+"Z"

def _active_problem(thread_state: Dict[str,Any]) -> Dict[str,Any] | None:
    prs = thread_state.get("problem_records", [])
    if not prs: return None
    prs_sorted = sorted(prs, key=lambda p: p.get("last_updated",""), reverse=True)
    return prs_sorted[0]

def _pp_titles(gpp: Dict[str,Any], ids: List[str]) -> List[str]:
    by_id = {p["id"]: p for p in (gpp or {}).get("pain_points", [])}
    out = []
    for pid in ids or []:
        t = by_id.get(pid, {}).get("title", pid)
        out.append(t)
    return out

def _brief_from(problem: Dict[str,Any], gpp: Dict[str,Any]) -> str:
    role = problem.get("employment_category","")
    pp_ids = problem.get("pain_points", [])
    pp_titles = _pp_titles(gpp, pp_ids)
    ins = problem.get("insights", {})
    # choose some commonly useful fields if present
    picks = []
    for fkey in ["git.pace.chunk_size","git.pace.ramp_rate","git.pace.parallelism","git.pace.checkpoint_frequency","git.kp.orientation"]:
        if fkey in ins:
            v = ins[fkey].get("value")
            picks.append(f"{fkey.split('.')[-1]}={v}")
    anchors = [it.get("anchor_id") for it in (problem.get("last_evidence_pack") or [])][:4]
    blocks = [
        f"Role: {role}",
        f"Pain points: {', '.join(pp_titles) or '—'}",
        f"Insights: {', '.join(picks) or '—'}",
        f"Evidence anchors: {', '.join(anchors) or '—'}",
    ]
    return " | ".join(blocks)

def update_and_persist_history(env: Dict[str,Any],
                               thread_state: Dict[str,Any],
                               step1: Dict[str,Any],
                               step2: Dict[str,Any],
                               step3: Dict[str,Any],
                               step4: Dict[str,Any],
                               step5: Dict[str,Any],
                               step6: Dict[str,Any]) -> Dict[str,Any]:

    prompt = (step1.get("request_envelope",{}) or {}).get("prompt_clean","")
    mapped_role = (step2.get("problem_context",{}) or {}).get("employment_category")
    mapped_pp = (step2.get("problem_context",{}) or {}).get("pain_points", [])
    mapping_conf = (step2.get("problem_context",{}) or {}).get("mapping_confidence", 0.0)
    answerability = (step5.get("pcc",{}) or {}).get("answerability","unknown")
    missing_fields = (step5.get("pcc",{}) or {}).get("missing_fields", [])
    survey = (step4 or {}).get("survey", [])
    evidence = (step6 or {}).get("results", [])

    # 1) Rolling history_summary (simple, size-limited string)
    hs = (thread_state.get("history_summary") or "").strip()
    new_line = f"[{_now_iso()}] user: {prompt}"
    combined = (hs + " " + new_line).strip()
    if len(combined) > 2000:
        # keep last 2000 chars
        combined = combined[-2000:]
    thread_state["history_summary"] = combined

    # 2) Append dialogue snippet to active problem
    pr = _active_problem(thread_state)
    if pr:
        pr.setdefault("dialogue_snippets", [])
        snippet = {
            "at": _now_iso(),
            "prompt": prompt,
            "employment_category": mapped_role,
            "pain_points": mapped_pp,
            "mapping_confidence": mapping_conf,
            "answerability": answerability,
            "missing_fields": missing_fields,
            "survey_len": len(survey),
            "evidence_anchors": [e.get("anchor_id") for e in (evidence or []) if e.get("anchor_id")]
        }
        pr["dialogue_snippets"].append(snippet)
        pr["dialogue_snippets"] = pr["dialogue_snippets"][-25:]  # cap to last 25

        # 3) Refresh planning_brief (compact, deterministic text)
        gpp = env.get("catalog_data",{}).get("gpp_taxonomy",{})
        pr["planning_brief"] = _brief_from(pr, gpp)
        pr["last_updated"] = _now_iso()

    # 4) Turn meta (for debugging or analytics)
    turn_meta = {
        "at": _now_iso(),
        "problem_id": pr.get("problem_id") if pr else None,
        "mapping_confidence": mapping_conf,
        "answerability": answerability,
        "missing_fields_count": len(missing_fields),
        "evidence_count": len(evidence or [])
    }

    return {"ok": True,
            "history_len": len(thread_state.get("history_summary","")),
            "dialogue_snippets_count": len((pr or {}).get("dialogue_snippets", [])),
            "planning_brief": (pr or {}).get("planning_brief", ""),
            "turn_meta": turn_meta}


def _convfirst_record(thread_state, res1, res4):
    # record last prompt signals + mark asked Stage-1 keys + bump turn index
    from agent.survey_policy import current_turn_index, record_asked
    try:
        turn_idx = current_turn_index(thread_state)
        sig = (res1 or {}).get('request_envelope',{}).get('prompt_signals',{})
        thread_state['last_prompt_signals'] = sig
        thread_state['last_intent'] = sig.get('intent','learn')
        prs = thread_state.get('problem_records') or []
        if prs:
            pr = prs[-1]
            keys = (res4 or {}).get('survey',{}).get('required_keys') or []
            if keys:
                record_asked(pr, list(dict.fromkeys(keys)), turn_idx)
        thread_state['turn_index'] = turn_idx + 1
    except Exception:
        pass

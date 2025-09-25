TONE_MAP={'frustrated':'empathetic_motivational','anxious':'calm_reassuring','confused':'clarifying_patient','confident':'direct_coach'}
DEFAULT_TONE='neutral'

import copy
from typing import Dict, Any, List

def _active_problem(thread_state: Dict[str, Any]) -> Dict[str, Any] | None:
    prs = thread_state.get("problem_records", [])
    if not prs:
        return None
    # Heuristic: last updated most recent
    prs_sorted = sorted(prs, key=lambda p: p.get("last_updated",""), reverse=True)
    return prs_sorted[0]

def _tone_from_context(role_id: str, pain_points: List[str]) -> str:
    # Simple heuristics; you can expand this mapping later
    p = ",".join(pain_points or [])
    emotional_ids = ["motivation", "imposter", "identity", "paralysis"]
    if any(k in p for k in emotional_ids):
        return "motivational"
    return "neutral"

def _length_from_missing(missing_count: int, base_target: int) -> Dict[str,int]:
    # If we are missing required insights, we keep the response focused to avoid premature long plans
    if missing_count == 0:
        return {"target": base_target, "max": int(base_target*2)}
    if missing_count <= 2:
        return {"target": max(300, int(base_target*0.8)), "max": max(600, int(base_target*1.2))}
    return {"target": 220, "max": 500}

def _answerability(missing_required: List[str]) -> str:
    if not missing_required:
        return "full"
    return "partial_needs_insights"

def _derive_missing_required(step3_binding: Dict[str, Any], problem: Dict[str, Any], git_catalog: Dict[str, Any]) -> List[str]:
    """step3_binding.required_insights are category IDs;
       expand children and see which are absent in the bound insights."""
    if not step3_binding or not step3_binding.get("required_insights"):
        return []
    required_cats = step3_binding["required_insights"]
    # build a set of child field_ids from catalog
    required_fields = set()
    for node in git_catalog.get("fields", []):
        if node.get("id") in required_cats:
            for ch in node.get("children", []):
                fid = ch.get("id")
                if fid:
                    required_fields.add(fid)
    have = set((problem or {}).get("insights", {}).keys())
    missing = sorted([f for f in required_fields if f not in have])
    return missing

def build_pcc(env: Dict[str, Any],
              thread_state: Dict[str, Any],
              step2: Dict[str, Any],
              step3: Dict[str, Any],
              step4: Dict[str, Any]) -> Dict[str, Any]:
    defaults = copy.deepcopy(env.get("pcc_defaults", {}))
    problem = _active_problem(thread_state) or {}
    role_id = problem.get("employment_category") or step2.get("problem_context",{}).get("employment_category")
    pp = problem.get("pain_points") or step2.get("problem_context",{}).get("pain_points", [])
    tone = _tone_from_context(role_id, pp)

    git_catalog = env.get("catalog_data",{}).get("git_insight_catalog",{})
    missing_required = _derive_missing_required(step3.get("binding",{}), problem, git_catalog)
    length = _length_from_missing(len(missing_required), defaults.get("target_tokens", 450))

    # retrieval scope is vault-only per your policy
    retrieval = {
        "mode": "vault_only",
        "anchors_scope": list((step2.get("debug",{}).get("pain_point_map",{}).get("ranked") or [])[:5]),  # debugging aids; Step 6 will replace with actual queries
        "top_k": 6,
        "rerank": True
    }

    sul = {
        "llm_enabled": True,                   # gated fallback is allowed
        "max_calls": 1,
        "model_hint": "local-small",           # e.g., llama 3–7B quantized
        "cite_or_decline": True
    }

    verifications = {
        "must_cite": True,
        "fact_check": "strict",
        "reasoning_trace": "compact"
    }

    structure = defaults.get("layered_template", ["Preface","Core Summary","Evidence","Checklist","Closer","Sources"])

    pcc = {
        "format": defaults.get("format","markdown"),
        "language": thread_state.get("session_profile",{}).get("preferred_language", defaults.get("language","en")),
        "tone": tone,
        "length": "detailed" if not missing_required else "concise",
        "target_tokens": length["target"],
        "max_tokens": length["max"],
        "structure": structure,
        "answerability": _answerability(missing_required),
        "missing_fields": missing_required,
        "retrieval": retrieval,
        "sul": sul,
        "verifications": verifications,
        "style": {
            "bullets_allowed": True,
            "use_checklists": True,
            "headers_from_structure": True
        },
        "citations": {
            "required": True,
            "style": "inline_brackets"   # Step 9 will render properly
        }
    }

    # Persist snapshot on the active problem (so UPA/Composer can read it later)
    if problem:
        problem["pcc_snapshot"] = pcc

    return {"ok": True, "pcc": pcc}

# tone from last prompt signals with confidence threshold
try:
    last_sig  = (thread_state or {}).get('last_prompt_signals', {})
    aff_label = last_sig.get('affect_label')
    aff_conf  = float(last_sig.get('affect_confidence') or 0.0)
    tone_profile = TONE_MAP.get(aff_label, DEFAULT_TONE) if aff_conf >= 0.60 else DEFAULT_TONE
    effective_pcc['tone_profile'] = tone_profile
    effective_pcc['micro_survey_style'] = (
        'supportive_minimal' if tone_profile in ('empathetic_motivational','calm_reassuring','clarifying_patient')
        else 'neutral_minimal'
    )
except Exception:
    pass

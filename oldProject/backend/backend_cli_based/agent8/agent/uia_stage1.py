import re
from datetime import datetime

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


import json
from typing import Dict, Any, List, Tuple
try:
    # Use the same orchestrator as composer so we don't change providers logic
    from .llm_orchestrator import generate_with_fallback
except Exception:  # pragma: no cover
    generate_with_fallback = None

def _fields_for_categories(git_catalog: dict, categories: List[str]) -> List[dict]:
    keep = set(categories or [])
    out = []
    for node in git_catalog.get("fields", []) or []:
        if node.get("id") in keep:
            for ch in node.get("children", []) or []:
                if ch.get("id"):
                    out.append(ch)
    return out

def _llm_assist(env: dict, text: str, required_categories: List[str]) -> List[dict]:
    """
    Optional LLM-aided extraction that maps free text to canonical field ids.
    Returns a list of insight dicts with source='nlp_llm'.
    """
    if not env or not isinstance(env, dict) or generate_with_fallback is None:
        return []
    policy = (env.get("thread_policy", {}) or {}).get("uia", {}) or {}
    if not policy.get("allow_llm_assist", False):
        return []

    git_cat = (env.get("catalog_data", {}) or {}).get("git_insight_catalog", {}) or {}
    fields = _fields_for_categories(git_cat, required_categories) or []
    if not fields:
        # fallback to all fields if categories not bound yet
        for node in git_cat.get("fields", []) or []:
            for ch in node.get("children", []) or []:
                if ch.get("id"):
                    fields.append(ch)
    if not fields:
        return []

    # Build a compact schema prompt
    lines = [
        "You are an information extractor. Infer values for any of the following canonical insight fields from the USER TEXT.",
        "Use ONLY the provided allowed values when 'type' is enum. If unsure, omit the field.",
        "Output pure JSON array: [{\"field_id\":\"...\",\"value\":\"...\"}] with no commentary."
    ]
    for ch in fields[:80]:  # cap to keep prompt small
        fid = ch.get("id","")
        typ = ch.get("type","text")
        if typ == "enum":
            vals = ", ".join(map(str, ch.get("values", []) or []))
            lines.append(f"- {fid} (enum): [{vals}]")
        else:
            lines.append(f"- {fid} (text)")
    system_prompt = "\n".join(lines)
    user_prompt = f"USER TEXT:\n{text[:4000]}"  # cap

    llm_cfg = env.get("llm_providers", {}) or {}
    res = generate_with_fallback(llm_cfg, system_prompt, user_prompt) if generate_with_fallback else {"ok": False}
    content = (res or {}).get("content","").strip() if isinstance(res, dict) else ""
    out: List[dict] = []
    if content:
        try:
            arr = json.loads(content)
            if isinstance(arr, dict):
                arr = [arr]
            for item in arr or []:
                fid = item.get("field_id")
                val = item.get("value")
                if not fid or val is None:
                    continue
                out.append({
                    "field_id": fid,
                    "value": val,
                    "confidence": 0.82,
                    "source": "nlp_llm",
                    "provenance": {"mode": "llm_assist"},
                    "evidence_refs": [],
                    "status": "proposed",
                    "updated_at": _now_iso(),
                })
        except Exception:
            pass
    return out

# Map short field ids to canonical catalog ids expected by PCC/answerability
CANON_ID = {
    "git.pace.chunk_size": "git.categories.pace_tolerance_chunk_size.mcq.chunk_size",
    "git.pace.ramp_rate": "git.categories.pace_tolerance_chunk_size.mcq.ramp_rate",
    "git.pace.parallelism": "git.categories.pace_tolerance_chunk_size.mcq.parallelism",
    "git.pace.checkpoint_frequency": "git.categories.pace_tolerance_chunk_size.mcq.checkpoint_frequency",
    "git.learning.primary_modality": "git.categories.learning_preferences_modalities.mcq.primary_modality",
    "git.learning.interactivity_level": "git.categories.learning_preferences_modalities.mcq.interactivity_level",
    "git.learning.social_context": "git.categories.learning_preferences_modalities.mcq.social_context",
    "git.learning.memory_supports": "git.categories.learning_preferences_modalities.mcq.memory_supports",
    "git.time.capacity_profile": "git.categories.time_energy_rhythm.mcq.capacity_profile",
    "git.time.peak_windows": "git.categories.time_energy_rhythm.mcq.peak_windows",
    "git.time.session_length_tolerance": "git.categories.time_energy_rhythm.mcq.session_length_tolerance",
    "git.time.cadence_style": "git.categories.time_energy_rhythm.mcq.cadence_style",
}


# Synonyms table to normalize free-text spans into canonical option values
VALUE_SYNONYMS = {
    "git.pace.chunk_size": {
        "micro": ["micro", "tiny", "5-10 min", "5 to 10", "5–10", "micro-bursts", "very small"],
        "small": ["small", "15-30 min", "15 to 30", "15–30", "bite-sized"],
        "medium": ["medium", "45-60 min", "45 to 60", "45–60", "one hour", "~1h"],
        "large": ["large", "90+ min", "90 plus", "deep work", "long block", "1.5h", "two hours"],
    },
    "git.pace.ramp_rate": {
        "conservative": ["conservative", "slow ramp", "gentle", "gradual", "step-by-step"],
        "balanced": ["balanced", "steady", "predictable"],
        "aggressive": ["aggressive", "fast", "hard jumps", "intense", "challenge quickly"],
    },
    "git.pace.parallelism": {
        "single_thread": ["single-thread", "single thread", "one thing", "one at a time", "focus only"],
        "dual_thread": ["dual-thread", "dual thread", "two tracks", "two things", "am/pm split"],
        "multi_thread": ["multi-thread", "3+", "several tracks", "many things", "juggling"],
    },
    "git.pace.checkpoint_frequency": {
        "continuous": ["continuous", "every task", "all the time", "per task"],
        "daily": ["daily", "end of day", "every day"],
        "weekly": ["weekly", "once a week", "each week"],
    },
    # Optional extra: knowledge processing orientation
    "git.kp.orientation": {
        "principle_first": ["principle-first", "principle first", "theory first", "concepts first"],
        "example_first": ["example-first", "example first", "examples first", "show me examples"],
        "inductive": ["inductive", "derive", "bottom-up"],
        "deductive": ["deductive", "apply theory", "top-down"],
    },
}


# Lightweight pattern recognizers (span-based)
PATTERNS = [
    (
        "git.pace.chunk_size",
        re.compile(
            r"\b(5[\-\–]?\s?10\s?min|10\s?min|micro(-?bursts)?|tiny|small|15[\-\–]?\s?30\s?min|30\s?min|medium|45[\-\–]?\s?60\s?min|60\s?min|one hour|~?1h|large|90\+?\s?min|deep work)\b",
            re.I,
        ),
    ),
    (
        "git.pace.ramp_rate",
        re.compile(r"\b(conservative|gradual|gentle|balanced|steady|predictable|aggressive|fast|intense|challenge)\b", re.I),
    ),
    (
        "git.pace.parallelism",
        re.compile(r"\b(single(-|\s)?thread|one at a time|focus only|dual(-|\s)?thread|two tracks|multi(-|\s)?thread|several tracks|juggling|3\+)\b", re.I),
    ),
    (
        "git.pace.checkpoint_frequency",
        re.compile(r"\b(continuous|every task|per task|daily|end of day|weekly|once a week)\b", re.I),
    ),
    (
        "git.kp.orientation",
        re.compile(r"\b(principle(-|\s)?first|theory first|concepts first|example(-|\s)?first|examples first|inductive|deductive|bottom-up|top-down)\b", re.I),
    ),
]


def _normalize(field_id: str, raw: str):
    raw_l = (raw or "").lower().strip()
    table = VALUE_SYNONYMS.get(field_id, {})
    for canon, syns in table.items():
        for s in syns:
            if s in raw_l:
                return canon, 0.85
    for canon in table.keys():
        if canon == raw_l:
            return canon, 0.70
    return raw_l[:50], 0.35


def extract(text: str):
    """Extract candidate insights from free text using span matches + normalization."""
    out = []
    for fid, rx in PATTERNS:
        for m in rx.finditer(text or ""):
            span = m.group(0)
            val, conf = _normalize(fid, span)
            canon_id = CANON_ID.get(fid, fid)  # canonicalize field id
            out.append(
                {
                    "field_id": canon_id,
                    "value": val,
                    "confidence": round(conf, 3),
                    "source": "nlp",
                    "provenance": {"span": span},
                    "evidence_refs": [],
                    "status": "proposed",
                    "updated_at": _now_iso(),
                }
            )
    return out


def merge(thread_state: dict, insights: list, problem_id: str | None = None):
    """Merge extracted insights into the active problem record (by confidence)."""
    merged = 0
    if problem_id:
        pr = None
        for p in thread_state.get("problem_records", []):
            if p.get("problem_id") == problem_id:
                pr = p
                break
        if pr is None:
            thread_state.setdefault("unbound_insights", []).extend(insights)
            return {"merged": len(insights)}
        pr.setdefault("insights", {})
        for ins in insights:
            fid = ins["field_id"]
            if fid in pr["insights"]:
                prev = pr["insights"][fid]
                hist = {
                    "value": prev.get("value"),
                    "confidence": prev.get("confidence", 0),
                    "source": prev.get("source", "nlp"),
                    "updated_at": prev.get("updated_at"),
                }
                prev.setdefault("history", []).append(hist)
                if ins["confidence"] >= prev.get("confidence", 0):
                    prev.update({k: ins[k] for k in ["value", "confidence", "source", "provenance", "status"]})
                    prev["updated_at"] = _now_iso()
            else:
                pr["insights"][fid] = ins
            merged += 1
    else:
        thread_state.setdefault("unbound_insights", []).extend(insights)
        merged = len(insights)
    return {"merged": merged}


def _children(git_catalog: dict, category_id: str):
    """Return children (fields) for a given category id from the git catalog."""
    for node in git_catalog.get("fields", []):
        if node.get("id") == category_id:
            return node.get("children", [])
    return []


def draft(required_categories: list, git_catalog: dict, existing: dict):
    """
    Build a small list of question dicts for fields that are required but missing.
    existing: current insights dict (canonical ids).
    """
    qs = []
    existing_keys = set(existing.keys()) if isinstance(existing, dict) else set()
    for cat in required_categories or []:
        for ch in _children(git_catalog, cat):
            fid = ch.get("id")
            if not fid:
                continue
            if fid in existing_keys:
                continue
            if ch.get("type") == "enum":
                qs.append(
                    {
                        "field_id": fid,
                        "type": "select",
                        "label": ch.get("label", fid.split(".")[-1].replace("_", " ").title()),
                        "options": ch.get("values", []),
                    }
                )
            else:
                qs.append(
                    {
                        "field_id": fid,
                        "type": "text",
                        "label": ch.get("label", fid.split(".")[-1].replace("_", " ").title()),
                    }
                )
    return qs


def uia_stage1_extract_and_draft(env: dict, thread_state: dict, step1: dict, step3: dict):
    """
    - Extract insights from prompt/history (canonical ids).
    - Merge into active problem.
    - Draft a *small* set of missing questions from the git_insight_catalog.
    """
    git_cat = (env.get("catalog_data", {}) or {}).get("git_insight_catalog", {}) or {}
    text = (
        (step1.get("request_envelope", {}) or {}).get("prompt_clean", "")
        + " "
        + (step1.get("request_envelope", {}) or {}).get("history_summary", "")
    ).strip()

    extracted = extract(text)

    problem_id = step3.get("binding", {}).get("problem_id") if step3.get("ok") else None
    required_categories = step3.get("binding", {}).get("required_insights", []) if step3.get("ok") else []

    merge_res = merge(thread_state, extracted, problem_id)

    existing = {}
    if problem_id:
        for p in thread_state.get("problem_records", []):
            if p.get("problem_id") == problem_id:
                existing = p.get("insights", {}) or {}
                break

    survey = draft(required_categories, git_cat, existing)
    return {
        "ok": True,
        "extracted_count": len(extracted),
        "merged_count": merge_res.get("merged", 0),
        "survey": survey,
    }

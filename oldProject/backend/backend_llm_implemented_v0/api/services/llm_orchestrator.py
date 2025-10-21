
import os
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# Optional OpenAI support. If keys not present, we fall back to a rule-based stub.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # change if needed

# Insight enums (keep in sync with your extractor/schema)
INSIGHT_ENUMS: Dict[str, List[str]] = {
    "goal_type": ["deliverable_shipped","performance_target","proficiency_level","behavior_change","stakeholder_signoff"],
    "deadline_profile": ["none","immediate_lt_1w","near_term_1_4w","mid_term_1_3m","long_term_gt_3m"],
    "tradeoff_priority": ["time","quality","scope","cost","risk"],
    "modality": ["text_first","visual","audio","hands_on"],
    "interactivity_level": ["passive_first","exercise_first","project_first"],
    "availability_windows": ["morning","midday","evening","night"],
    "session_length": ["micro_10_20","standard_25_45","deep_60_90","marathon_ge_120"],
    "chunk_size": ["micro","small","medium","large"],
    "ramp_rate": ["conservative","balanced","aggressive"],
    "parallelism": ["single","dual","multi"],
    "checkpoint_frequency": ["continuous","daily","weekly","milestone_only"],
}

REQUIRED_FIELDS = [
    "goal_type","deadline_profile","tradeoff_priority",
    "modality","interactivity_level",
    "availability_windows","session_length",
    "chunk_size","ramp_rate","parallelism","checkpoint_frequency"
]

NEXT_MISSING_ORDER = [
    "goal_type","deadline_profile","tradeoff_priority","modality","interactivity_level",
    "session_length","chunk_size","ramp_rate","checkpoint_frequency","availability_windows","parallelism"
]

SYSTEM_PROMPT = """You are the User Analysis Agent (UAA) for Relativity AI, focused on skill development and brain training for entry-level tech jobs.
Goal: Analyze the user's problem, gather data through natural conversation, and create a perfect problem statement to pass to the User Planning Agent (UPA).

Operating rules:
- Scope: strictly “IT” topics. If out of scope like "BUSINESS/ART, ETC", redirect politely and ask to narrow.
- No planning: do not produce plans, roadmaps, curricula, or schedules. Your job is insight gathering only.
- Conversational strategy: collect missing insights ONE at a time with short, natural questions. Acknowledge answers briefly.
- Evidence use: you will receive a RAG evidence pack. Use it only if it directly helps explain or clarify a user question; otherwise ignore it. Never invent sources.
- Greetings/small talk: respond briefly then ask the next most valuable missing insight.
- If the user asks an informational question within IT field(e.g., “explain…”, “how to…”, “what is…”), first give a concise 2–4 sentence answer using RAG evidence when useful.
- Completion: when all required insights are filled, emit READY_FOR_PLANNING with a Problem Statement JSON. If the user asks to plan before that, emit MISSING_INSIGHTS and provide MCQ options.

Required insights (v1):
goal_type, deadline_profile, tradeoff_priority,
modality (multi), interactivity_level,
availability_windows (multi), session_length,
chunk_size, ramp_rate, parallelism, checkpoint_frequency.

Output format (valid JSON only):
{
  "type": "ASK_INSIGHT" | "SMALL_TALK" | "ACK" | "MISSING_INSIGHTS" | "READY_FOR_PLANNING",
  "message": "1–3 sentence natural reply",
  "insight_request": { "field_id": "...", "options": ["..."] } | null,
  "insight_update": { "field_id": "...", "value": "... or [...]", "confidence": 0.9 } | null,
  "missing": ["..."] | null,
  "problem_statement": {
    "scope": "junior_it",
    "summary": "1 short paragraph",
    "insights": { "<field>": "<value or [values]>", ... }
  } | null,
  "use_evidence": true | false
}
Return only JSON. Do not include markdown fences or explanations.
"""

DEVELOPER_PROMPT = {
    "insight_enums": INSIGHT_ENUMS,
    "required_fields": REQUIRED_FIELDS,
    "next_missing_order": NEXT_MISSING_ORDER,
    "policies": [
        "Always pick the first missing field from next_missing_order to ask next.",
        "When the user’s utterance clearly sets a field, include insight_update.",
        "If user says 'go to planning' and fields are missing, set type='MISSING_INSIGHTS' and either ask the next missing field with MCQ or list all missing.",
        "If the last user turn is greeting/acknowledgment/yes-no, set type='SMALL_TALK' and ask ONE next field.",
        "Keep use_evidence=false unless a user question specifically benefits from evidence."
    ]
}

def _is_smalltalk(prompt: str) -> bool:
    t = prompt.strip().lower()
    return t in {"hi","hello","hey","thanks","thank you","yo","sup"} or len(t) <= 3

def _first_missing(insight_state: Dict[str, Any]) -> Optional[str]:
    for f in NEXT_MISSING_ORDER:
        if f not in insight_state or not insight_state[f] or "value" not in insight_state[f]:
            return f
    return None

def _normalize_state_for_llm(insight_state: Dict[str, Any]) -> Dict[str, Any]:
    # Keep only field->value for compactness
    out = {}
    for k,v in (insight_state or {}).items():
        if isinstance(v, dict) and "value" in v:
            out[k] = v["value"]
    return out

def _build_user_payload(user_prompt: str, chat_history: List[Dict[str,str]], insight_state: Dict[str,Any], evidence_pack: Dict[str,Any]) -> str:
    payload = {
        "user_prompt": user_prompt,
        "chat_history": chat_history[-8:],  # last 8 turns
        "insight_state": _normalize_state_for_llm(insight_state),
        "evidence_pack": evidence_pack or {"results":[]}
    }
    return json.dumps(payload)

def _fallback_policy(user_prompt: str, insight_state: Dict[str,Any]) -> Dict[str,Any]:
    # Rule-based behavior if no API key or model failure.
    if _is_smalltalk(user_prompt):
        nxt = _first_missing(insight_state) or ""
        options = INSIGHT_ENUMS.get(nxt, [])
        return {
            "type": "SMALL_TALK",
            "message": "Hi! I help junior IT folks get unstuck. To tailor things: " + (f"what’s your choice for {nxt.replace('_',' ')}?" if nxt else "we can start when you’re ready."),
            "insight_request": {"field_id": nxt, "options": options} if nxt else None,
            "insight_update": None,
            "missing": None,
            "problem_statement": None,
            "use_evidence": False
        }
    # Else ask next missing
    nxt = _first_missing(insight_state)
    if nxt:
        return {
            "type": "ASK_INSIGHT",
            "message": f"Quick one: what’s your preference for {nxt.replace('_',' ')}?",
            "insight_request": {"field_id": nxt, "options": INSIGHT_ENUMS.get(nxt, [])},
            "insight_update": None,
            "missing": None,
            "problem_statement": None,
            "use_evidence": False
        }
    # Ready case
    return {
        "type": "READY_FOR_PLANNING",
        "message": "I have everything I need. Ready for planning.",
        "insight_request": None,
        "insight_update": None,
        "missing": None,
        "problem_statement": {
            "scope": "junior_it",
            "summary": "Problem statement ready (fallback).",
            "insights": _normalize_state_for_llm(insight_state)
        },
        "use_evidence": False
    }

def call_llm(user_prompt: str, chat_history: List[Dict[str,str]], insight_state: Dict[str,Any], evidence_pack: Dict[str,Any]) -> Dict[str,Any]:
    """
    Returns the structured JSON per the system prompt. If OpenAI is not configured
    or JSON parsing fails, returns a rule-based fallback.
    """
    # Evidence utility heuristic: blank evidence for pure smalltalk / short answers
    if _is_smalltalk(user_prompt):
        evidence_pack = {"results": []}

    if not OPENAI_API_KEY:
        return _fallback_policy(user_prompt, insight_state)

    # Build messages for OpenAI Chat Completions
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        messages = [
            {"role":"system", "content": SYSTEM_PROMPT},
            {"role":"system", "name":"developer", "content": json.dumps(DEVELOPER_PROMPT)},
            {"role":"user", "content": _build_user_payload(user_prompt, chat_history, insight_state, evidence_pack)}
        ]
        print("LLM call messages:", messages)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=500
        )
        raw = resp.choices[0].message.content.strip()
        # ensure JSON
        # remove backticks if model added markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
        data = json.loads(raw)
        return data
    except Exception as e:
        # Fall back
        return _fallback_policy(user_prompt, insight_state)

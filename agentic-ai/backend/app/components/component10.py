# app/components/component10.py
from __future__ import annotations
from fastapi import HTTPException
import json
import re
from typing import Any, Dict, List, Literal, Optional, Tuple, TypedDict

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.settings import settings
from app.repositories.insight_vault_repo import InsightVaultRepo

# 👇 Adjust these imports to wherever you actually defined them
from app.repositories.vault_repo  import list_ec_options, list_skill_options_for_ec, get_active_vault_version
from app.services.insight_completion import list_fully_taken_batches
from app.repositories.chat_repo import get_chat_state

from app.core.llm import complete_json as llm_complete_json


Stage = Literal["employment_category", "skills", "insights", "none"]


class EncouragementResult(TypedDict):
    stage: Stage
    question: str


# ---------------------------
# Public entrypoint
# ---------------------------

async def component10(
    db: AsyncIOMotorDatabase,
    *,
    chat_id: str,
    user_id: str,
    user_msg: str,
    c06: Dict[str, Any],
    c07: Dict[str, Any],
    step,
    language: str = "en",
) -> EncouragementResult:
    """
    Decide a single encouragement stage and generate ONE question (via LLM).
    Output shape: {"stage": "...", "question": "..."}.
    """
    print("=="*30);print(f" ----| Starting Component 10 |")

    await step(10.0, "Component 10: start")

    version = await _active_version_or_404(db)

    # ---- Read chat UIA state
    chat_state = await get_chat_state(db, chat_id)
    ec_current: Optional[str] = chat_state.get("employment_category_id") if chat_state else None
    skills_done: bool = _skills_already_recorded(chat_state)

    action: str = (c06 or {}).get("uia_action") or "none"
    surveys_prepared: int = int((c07 or {}).get("surveysPrepared") or 0)
    touched_batch_ids: List[str] = (c07 or {}).get("touchedBatchIds") or []

    # ---- Stage selection

    # Stage A — Employment Category
    if ec_current is None and action != "show_ec_survey":
        print(" ------| Stage A: Employment Category needed")
        await step(10.1, "C10: Stage=employment_category")
        ec_opts = await list_ec_options(db, version)  # [{id,label},...]
        prompt = _build_ec_prompt(user_msg=user_msg, ec_options=ec_opts, language=language)
        return await _call_llm_single_question(prompt, expect_stage="employment_category")

    # Stage B — Skills
    if not skills_done and action != "show_skills_survey":
        print(" ------| Stage B: Skills needed")
        # if ec_current is None:
        #     # Safety: upstream guarantees this shouldn't happen, but avoid hard-crash.
        #     await step(10.2, "C10: Stage=skills blocked (no EC); returning none")
        #     return {"stage": "none", "question": ""}

        await step(10.2, "C10: Stage=skills")

        # We want the current EC's display label for better phrasing
        ec_opts = await list_ec_options(db, version)
        ec_label = _label_for_id(ec_opts, ec_current) or "your chosen role"

        skill_opts = await list_skill_options_for_ec(db, version, ec_current)
        prompt = _build_skills_prompt(
            user_msg=user_msg,
            ec_label=ec_label,
            skill_options=skill_opts,
            language=language,
        )
        return await _call_llm_single_question(prompt, expect_stage="skills")

    # Stage C — Insights
    # only encourage if no prepared survey from C07
    if surveys_prepared != 100:
        print(" ------| Stage C: Insights encouragement")
        await step(10.3, "C10: Stage=insights (finding first eligible batch)")
        complete_batches = await list_fully_taken_batches(db, chatId=chat_id)
        repo = InsightVaultRepo(db)
        batches_for_comp10 = await repo.list_batches_in_order(include_answers=True)

        target = _pick_first_eligible_batch(batches_for_comp10, touched_batch_ids, complete_batches)

        # if target:
        #     # Build a compact list of insight items with relevant answer texts to hint the LLM
        #     insight_items = _select_insight_items_with_relevant_answers(
        #         user_msg=user_msg,
        #         insights=target["insights"],  # [{insightId, question, isMultiSelect, answers: {A:{text,aliases},...}}, ...]
        #         k_items=1,
        #         k_answers=4,
        #     )
        #     prompt = _build_insights_prompt_with_answers(
        #         user_msg=user_msg,
        #         batch_id=target["batchId"],
        #         items=insight_items,  # [{insightId, question, mentionAnswers:[str,...]}]
        #         language=language,
        #     )
        #     return await _call_llm_single_question(prompt, expect_stage="insights")
        
        if target:
            insight = _pick_best_insight_single(user_msg, target["insights"])
            if insight:
                prompt = _build_insights_prompt_forced_options_creative(
                    user_msg=user_msg,
                    batch_id=target["batchId"],
                    insight=insight,  # dict with {insightId, question, isMultiSelect, answers:{A:{text,aliases},...}}
                    language=language,
                )
                result = await _call_llm_single_question(prompt, expect_stage="insights")

                # Guard: ensure question actually includes at least one canonical answer token
                canonical = _canonical_answer_list(insight.get("answers") or {})
                if not _question_mentions_any(result["question"], canonical):
                    # Deterministic safe fallback (still one sentence)
                    fallback_q = _deterministic_insight_question(insight)
                    return {"stage": "insights", "question": fallback_q}

                return result

    await step(10.9, "C10: no encouragement")
    return {"stage": "none", "question": ""}


# ---------------------------
# Prompt builders
# ---------------------------

def _build_ec_prompt(
    *, user_msg: str, ec_options: List[Dict[str, str]], language: str
) -> str:
    shortlist = _shortlist_by_relevance(user_msg, ec_options, label_key="label", k=4)

    ec_lines = "\n".join(f"- {o['id']} → {o['label']}" for o in ec_options)
    likely = ", ".join(o["label"] for o in shortlist)

    return f"""SYSTEM:
You generate one encouraging, concise question that nudges the user to state their employment category next.
Use only the provided categories; do not invent new ones. One sentence only. Friendly, clear, actionable.
Reply as strict JSON only: {{"stage":"employment_category","question":"..."}}
The JSON must be the only content in your response.

USER:
User message: <<{user_msg}>>

Employment categories (id → label):
{ec_lines}

If helpful, you may reference 2–4 likely labels inline (e.g., {likely}) but keep it within ONE sentence.
Language: {language}.
""".strip()


def _build_skills_prompt(
    *, user_msg: str, ec_label: str, skill_options: List[Dict[str, str]], language: str
) -> str:
    shortlist = _shortlist_by_relevance(user_msg, skill_options, label_key="label", k=4)

    skill_lines = "\n".join(f"- {o['id']} → {o['label']}" for o in skill_options)
    likely = ", ".join(o["label"] for o in shortlist)

    return f"""SYSTEM:
Generate one concise, encouraging question that nudges the user to name the skill areas they want to develop next for the specified employment category.
Use only the provided skill categories; do not invent. One sentence only.
Reply as strict JSON only: {{"stage":"skills","question":"..."}}
The JSON must be the only content in your response.

USER:
User message: <<{user_msg}>>
Employment category: {ec_label}

Skill categories (id → label):
{skill_lines}

If helpful, mention 2–4 likely categories inline (e.g., {likely}) but keep it within ONE sentence.
Language: {language}.
""".strip()


def _build_insights_prompt_with_answers(
    *,
    user_msg: str,
    batch_id: str,
    items: List[dict],  # [{"insightId","question","mentionAnswers":[str,...]}]
    language: str,
) -> str:
    """
    Builds a compact prompt: each insight with 2–3 candidate answer texts that the LLM
    MAY mention inline. We still require ONE sentence output and JSON-only.
    """
    lines = []
    for it in items:
        mentions = ", ".join(f"“{m}”" for m in it.get("mentionAnswers") or [])
        line = f"- {it['insightId']} → {it['question']}"
        if mentions:
            line += f"\n  Candidate answers to (optionally) mention: {mentions}"
        lines.append(line)

    block = "\n".join(lines)

    return f"""SYSTEM:
Generate one concise, encouraging question that nudges the user to share a pain point related to the provided batch.
Use only the provided insight topics and (optionally) their listed candidate answer texts; do not invent new options.
One sentence only. Output must be strict JSON: {{"stage":"insights","question":"..."}}
JSON must be the only content in your response.

USER:
User message: <<{user_msg}>>
Target batch: {batch_id}

Batch insights (id → question) with candidate answers you MAY weave into the sentence:
{block}

Write ONE sentence inviting the user to describe where they struggle most in this batch.
Do NOT list all options; at most weave 2–3 relevant phrases naturally. Avoid generic choices like “Other”.
Language: {language}.
""".strip()

def _build_insights_prompt_forced_options(
    *,
    user_msg: str,
    batch_id: str,
    insight: dict,   # includes question, isMultiSelect, answers
    language: str,
) -> str:
    """
    Build a prompt that FORCES the model to include canonical answer labels in the one-sentence question.
    This ensures the user's reply will mirror allowed options, enabling Comp-7 to capture it.
    """
    question = insight.get("question") or "Which option applies to you"
    is_multi = bool(insight.get("isMultiSelect"))
    options = _canonical_answer_list(insight.get("answers") or {})
    # Cap options to a reasonable length if necessary (but usually fine)
    # options = options[:7]

    chooser_phrase = "choose any of" if is_multi else "choose one of"
    options_inline = _join_oxford(options)
    # Example target: "What are the primary learning modes that stick for you—choose any of: Reading, Videos, or Hands-on practice (reply with the exact words)?"

    return f"""SYSTEM:
You must write ONE sentence that directly asks the user to answer the specific insight question AND explicitly list the allowed options (using the exact labels provided).
The sentence must include the chooser phrase (“{chooser_phrase}”), the comma-separated options, and the parenthetical “(reply with the exact words)”.
Do not invent options or paraphrase labels. Output strict JSON only: {{"stage":"insights","question":"..."}}
The JSON must be the only content in your response.

USER:
User message: <<{user_msg}>>
Target batch: {batch_id}

Insight question:
- {question}

Allowed options (canonical labels; use exactly as written):
- {options_inline}

Write ONE sentence that asks the insight question and enumerates these options inline using this pattern:
“{question}—{chooser_phrase}: {options_inline} (reply with the exact words)?”

Language: {language}.
""".strip()

def _build_insights_prompt_forced_options_creative(
    *,
    user_msg: str,
    batch_id: str,
    insight: dict,   # includes question, isMultiSelect, answers
    language: str,
) -> str:
    """
    Creative, persuasive single-sentence prompt that STILL enumerates the exact canonical labels.
    - Never says 'choose any of' or 'choose one of'.
    - May include a tiny context hook if available.
    - Must include '(reply with the exact words)' at the end.
    """
    question = (insight.get("question") or "Which option applies to you").rstrip(" ?")
    options = _canonical_answer_list(insight.get("answers") or {})
    options_inline = _join_oxford(options)

    # Short context bridge (optional)
    hook = _make_context_hook(user_msg, insight)
    hook_prefix = (hook + " ") if hook else ""

    # Style guardrails for the LLM
    style_rules = (
        "Tone: warm, encouraging, coach-like. Plain language. One sentence only. "
        "Be specific but conversational; avoid dry phrases like 'choose any of' or 'enumerate'. "
        "The sentence MUST include ALL options exactly as written, separated by commas with 'or' before the last item. "
        "End with '(reply with the exact words)'."
    )

    # Example target shape shown to the LLM (NB: it will reword but keep the structure)
    exemplar = f'{hook_prefix}{question} — is it {options_inline}? (reply with the exact words)'

    return f"""SYSTEM:
You will write ONE creative, persuasive, and concise question that nudges the user to answer the insight.
{style_rules}
Output strict JSON only: {{"stage":"insights","question":"..."}}
The JSON must be the only content in your response.

USER:
User message: <<{user_msg}>>
Target batch: {batch_id}

Insight question (use this idea, but feel free to rephrase naturally):
- {question}

Allowed options (canonical labels; include ALL of these exactly as written):
- {options_inline}

Write ONE sentence that sounds like a friendly coach and includes a tiny hook if provided:
Hook (optional): "{hook_prefix.strip()}"

Aim for ~18–32 words, natural connectors, and a smooth lead-in.
For example (do NOT copy verbatim): "{exemplar}"
Language: {language}.
""".strip()



# ---------------------------
# Helpers
# ---------------------------

async def _active_version_or_404(db) -> str:
    version = await get_active_vault_version(db)
    if not version:
        raise HTTPException(status_code=404, detail="No active vault")
    return version


def _skills_already_recorded(chat_state: Optional[dict]) -> bool:
    if not chat_state:
        return False
    if chat_state.get("let_system_decide") is True:
        return True
    skills = chat_state.get("skills_selected") or []
    return len(skills) > 0


def _label_for_id(options: List[Dict[str, str]], _id: str) -> Optional[str]:
    for o in options:
        if str(o.get("id")) == str(_id):
            return o.get("label")
    return None


def _shortlist_by_relevance(
    user_msg: str,
    options: List[Dict[str, str]],
    *,
    label_key: str = "label",
    k: int = 4,
) -> List[Dict[str, str]]:
    """
    Very-lightweight ranking: case-insensitive substring hits of label terms in user_msg.
    Stable fallback to original order if all scores equal.
    """
    text = (user_msg or "").lower()
    scored: List[Tuple[int, Dict[str, str]]] = []
    for o in options:
        label = (o.get(label_key) or "").lower()
        score = 0
        if not label:
            scored.append((score, o))
            continue
        # score by occurrences of label tokens in the user text
        tokens = [t for t in re.split(r"[^a-z0-9+]+", label) if t]
        score = sum(1 for t in tokens if t and t in text)
        scored.append((score, o))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [o for _, o in scored[:k]]


def _pick_first_eligible_batch(
    batches_for_comp10: List[Dict[str, Any]],
    touched_batch_ids: List[str],
    complete_batches: List[str],
) -> Optional[Dict[str, Any]]:
    touched = set(touched_batch_ids or [])
    complete = set(complete_batches or [])
    for b in (batches_for_comp10 or []):
        bid = b.get("batchId")
        if not bid:
            continue
        if bid not in touched and bid not in complete:
            return b
    return None

def _is_generic_answer_label(label: str) -> bool:
    s = (label or "").strip().lower()
    if not s:
        return False
    generic = {"other", "none", "none of these", "n/a", "not applicable", "not sure"}
    return s in generic or any(s.startswith(g) for g in generic)


def _score_answer_relevance(user_msg: str, ans: dict) -> int:
    """
    Lightweight score: count of alias/keyword hits in the user message.
    """
    text = (user_msg or "").lower()
    score = 0
    label = (ans.get("text") or "").lower()
    if label and label in text:
        score += 2  # label match
    for a in (ans.get("aliases") or []):
        a = (a or "").lower()
        if a and a in text:
            score += 1
    return score


def _select_insight_items_with_relevant_answers(
    *,
    user_msg: str,
    insights: List[dict],
    k_items: int = 3,
    k_answers: int = 3,
) -> List[dict]:
    """
    From the batch insights, pick up to k_items. For each, choose up to k_answers
    answer texts to *mention* (ranked by alias/label hits), excluding generic options
    like 'Other' / 'None of these'. If no hits, choose the first non-generic answers.
    Returns: [{"insightId","question","mentionAnswers":[str,...]}, ...]
    """
    trimmed: List[dict] = []
    for ins in insights:
        answers_map = ins.get("answers") or {}
        # Flatten answers while keeping order (A,B,C,...)
        flat = []
        for key in sorted(answers_map.keys()):
            obj = answers_map[key] or {}
            label = obj.get("text") or ""
            if _is_generic_answer_label(label):
                continue
            flat.append({
                "key": key,
                "text": label,
                "aliases": obj.get("aliases") or [],
            })

        # Rank by relevance to user_msg
        scored = [( _score_answer_relevance(user_msg, a), a ) for a in flat]
        scored.sort(key=lambda t: t[0], reverse=True)

        # If no positive matches, keep the first few non-generic as neutral suggestions
        picked = [a["text"] for s, a in scored if s > 0][:k_answers]
        if not picked:
            picked = [a["text"] for _, a in scored][:k_answers]

        trimmed.append({
            "insightId": ins.get("insightId"),
            "question": ins.get("question"),
            "mentionAnswers": picked,
        })

        if len(trimmed) >= k_items:
            break

    return trimmed

async def _call_llm_single_question(
    prompt: str,
    *,
    expect_stage: Literal["employment_category", "skills", "insights"],
) -> EncouragementResult:
    """
    Calls the LLM and enforces a tiny JSON schema: {"stage":"...","question":"..."}.
    If parsing fails, returns a safe fallback question for the expected stage.
    """
    # print(" ------| C10: LLM prompt:\n", prompt)
    try:
        # print(" ------| C10: LLM prompt completion call...")
        raw = await llm_complete_json(
            prompt=prompt,
            temperature=0.7,
            max_tokens=180,
        )
        data = _extract_json_object(raw)
        stage = data.get("stage")
        question = (data.get("question") or "").strip()
        if stage != expect_stage:
            stage = expect_stage
        if question and not question.endswith("?"):
            question += "?"
        if not question:
            raise ValueError("Empty question")
        return {"stage": stage, "question": question}
    except Exception:
        # Fallback phrasing
        fallback = {
            "employment_category": "Which employment category should we focus on next?",
            "skills": "For this role, which skill areas would you like to prioritize next?",
            "insights": "Where do you feel most stuck within this area right now?",
        }[expect_stage]
        return {"stage": expect_stage, "question": fallback}


def _extract_json_object(text: str) -> Dict[str, Any]:
    """
    Robustly extract the first {...} JSON object from model output and parse it.
    """
    if not text:
        return {}
    # If it already looks like JSON, try straight parse first
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            pass
    # Fallback: find first balanced {...}
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        blob = s[start : end + 1]
        return json.loads(blob)
    # Last resort
    return {}


# ------------------- new Updated insight stage helpers -----------

def _canonical_answer_list(answers_map: dict) -> List[str]:
    """Return canonical answer labels (answers[*].text) excluding generic ones."""
    labels = []
    for key in sorted(answers_map.keys()):
        obj = answers_map.get(key) or {}
        text = (obj.get("text") or "").strip()
        if text and not _is_generic_answer_label(text):
            labels.append(text)
    return labels


def _rank_insight_by_relevance(user_msg: str, insight: dict) -> int:
    """
    Score an insight by matches between user_msg and its answers (label + aliases).
    """
    text = (user_msg or "").lower()
    score = 0
    for key, obj in (insight.get("answers") or {}).items():
        lab = (obj.get("text") or "").lower()
        if lab and lab in text:
            score += 2
        for alias in (obj.get("aliases") or []):
            a = (alias or "").lower()
            if a and a in text:
                score += 1
    return score


def _pick_best_insight_single(user_msg: str, insights: List[dict]) -> Optional[dict]:
    """
    Choose exactly one insight to ask next.
    Prefer the highest relevance; fallback to first.
    """
    if not insights:
        return None
    scored = [( _rank_insight_by_relevance(user_msg, ins), idx, ins ) for idx, ins in enumerate(insights)]
    scored.sort(key=lambda t: (t[0], -t[1]), reverse=True)  # relevance desc, stable
    return scored[0][2]


def _join_oxford(items: List[str]) -> str:
    """Return an Oxford-style comma list with 'or' before the last item."""
    items = [s for s in items if s]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} or {items[1]}"
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def _deterministic_insight_question(insight: dict) -> str:
    """
    One-sentence fallback that enumerates canonical options so Comp-7 can match.
    Respects isMultiSelect to say 'choose any' vs 'choose one'.
    """
    q = (insight.get("question") or "Which option applies to you").rstrip(" ?")
    is_multi = bool(insight.get("isMultiSelect"))
    options = _canonical_answer_list(insight.get("answers") or {})
    opts_text = _join_oxford(options)
    chooser = "choose any of" if is_multi else "choose one of"
    # single sentence with em dash; ask to reply with exact words
    return f"{q}—{chooser}: {opts_text} (reply with the exact words)?"


def _question_mentions_any(question: str, tokens: List[str]) -> bool:
    s = (question or "").lower()
    return any((t or "").lower() in s for t in tokens if t)

# helpers (near other helpers)

def _make_context_hook(user_msg: str, insight: dict) -> str:
    """
    Returns a short, natural hook if the user message contains any label/alias for this insight.
    e.g., 'Since you mentioned videos,' or 'Given you like hands-on work,'.
    Empty string if no good match.
    """
    text = (user_msg or "").lower()
    hits = []
    for obj in (insight.get("answers") or {}).values():
        label = (obj.get("text") or "").strip()
        aliases = obj.get("aliases") or []
        if not label:
            continue
        if label.lower() in text:
            hits.append(label)
            break
        for a in aliases:
            if (a or "").lower() in text:
                hits.append(label)
                break
    if not hits:
        return ""
    # pick one and turn into a natural clause
    lab = hits[0]
    # a couple of friendly variants; keep it very short
    variants = [
        f"Since you mentioned {lab.lower()},",
        f"Given you lean toward {lab.lower()},",
        f"Because {lab.lower()} came up,",
        f"If {lab.lower()} helps you,",
    ]
    return variants[0]

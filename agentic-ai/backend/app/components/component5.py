# app/components/component5.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional, TypedDict

from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.core.llm import complete_json as llm_complete_json

class C05Result(TypedDict, total=False):
    proceed: bool
    message: Optional[str]  # present only when proceed == False

FRIENDLY_FALLBACK = (
    "This User Analysis Agent doesn’t write or run code; it clarifies your Data Scientist path by identifying your role, "
    "priority skills, and pain points to drive a personalized learning plan."
)

# PROMPT_CORE = """Role: You are the Decision Gate for Relativity AI’s User Analysis Agent. Decide if a user prompt is in scope.
# Output contract: Return exactly one JSON object, with no additional text.

# JSON format
# • In scope:
# {"proceed": true}
# • Out of scope:
# {"proceed": false, "message": "<concise statement for the frontend (no questions)>"}
# Message rules for out-of-scope:
# - Exactly ONE declarative sentence.
# - Friendly and informative (no questions, no requests, no “please”).
# - Start by naming the boundary (why it’s out of scope), then in the same sentence add what this agent DOES do.

# What counts as “in scope” — set {"proceed": true} if any is true:
# 1) Small talk / general niceties that don’t require work products. (Remember: this platform is the User Analysis Agent only—no coding, no production actions.)
# 2) User Analysis (Data Scientist focus): identifying the DS role, relevant skills, strengths/weaknesses, pain points and bottlenecks; transparency about how segments/insights are collected; self-assessment, planning, or coaching on alignment, capability gaps, decision stalls, learning loops, learning modes, onboarding, problem-solving posture, unstuck steps, practice cadence, accountability, constraints, or fear-avoidance.
# 3) DS/ML guidance (design/evaluation level, not execution/coding) with a clear task type, success signal, data reference, DS lifecycle activity, and no regulated judgments.
# 4) DS roles/specializations & capabilities (design/guidance scope): NLP, CV, Recommenders, Causal/Experimentation, Forecasting/Time-Series, GenAI/LLM app work.
# 5) DS deliverables (non-executing): EDA report, feature spec, model/evaluation write-up, experiment design/readout, dashboard specification, prototype/API design (not implementation).
# 6) Foundational DS competencies—analysis/guidance only (no coding/ops execution).
# 7) Design work that avoids unsafe access.
# 8) Advice artifacts: advice, plans, rubrics, checklists (not clinical/legal determinations).
# 9) Process intelligence: problem–solution summaries, criteria rationales, plan decisions, user-identification insights (UIA), friction scans, plan fine-tuning.
# 10) Purpose & principles: questions about the system’s purpose/principles or how work fits this platform’s flow.
# 11) Personalization inputs to tailor advice.

# Always out of scope — return {"proceed": false, "message": "..."}:
# • Non-DS tasks (e.g., physical repair, legal filing).
# • The user expects to provide a plan to enhance skills.
# • Guaranteed outcomes or irreversible actions without review.
# • Unrelated expertise (e.g., chip design, mechanical engineering).
# • Management authority asks (promotion, compensation decisions).
# • Exams/assessments on behalf of a user or impersonation.
# • Hands-on production access or security-sensitive operations without permission.
# • Coding work or code generation.
# • Executing/operating a plan on the user’s behalf.
# • Identity verification or profiling beyond declared consent.

# Helping facts (for composing the out-of-scope message):
# Relativity AI’s current product is the User Analysis Agent: it does NOT write or run code or operate systems; it helps you clarify your Data Scientist path by identifying your employment category, prioritizing skills, and surfacing pain points to power a personalized learning plan.

# Special handling:
# - If the user asks “what is the system / what can you do / what is Relativity AI,” treat it as out-of-scope for downstream components and respond with a single-sentence system explainer per the rule above, in this case dont say its out of scope directly but explain about the system.
# - If there is a an encouragement question asking for something from the user in the context, and user asking about outofscope one, first explain that this is out of scope and then remind them about the previous encouragement question.
# """

# PROMPT_CORE = """Role: You are the Decision Gate for Relativity AI’s User Analysis Agent. Decide if a user prompt is in scope.
# Output contract: Return exactly one JSON object, with no additional text.

# JSON format
# • In scope:
# {"proceed": true}
# • Out of scope:
# {"proceed": false, "message": "<friendly boundary + brief system description; if a prior encouragement exists, append a short re-ask>"} 

# General rules
# - Output exactly one JSON object with keys: proceed (bool) and, when false, message (string).
# - The message may be 1–2 sentences. Keep it concise and friendly.
# - When out-of-scope, FIRST explain the boundary and what this agent DOES do, THEN (if a prior encouragement question exists in CONTEXT) re-ask it briefly to guide the user back on track.
# - If re-asking, preserve any canonical option labels EXACTLY as written; you may lightly rephrase the lead-in but keep the options untouched.
# - Do not include extra keys, markdown, or commentary.

# Important
# - Always check if the user prompt is an answer to the previous encouragement question and if it is then its in-scope.
# - If the user is talking about skills or an employement category then it is in-scope(even contaning a single word about those accept them)
# - If the user is asking any information about data science field or data scientist roles (ex- 'Explain me about data science'/'what is data science'), then it is in-scope

# What counts as “in scope” — set {"proceed": true} if any is true:
# 1) Small talk / general niceties that don’t require work products. (Remember: this platform is the User Analysis Agent only—no coding, no production actions.)
# 2) User Analysis (Data Scientist focus): identifying the DS role, relevant skills, strengths/weaknesses, pain points and bottlenecks; transparency about how segments/insights are collected; self-assessment, planning, or coaching on alignment, capability gaps, decision stalls, learning loops, learning modes, onboarding, problem-solving posture, unstuck steps, practice cadence, accountability, constraints, or fear-avoidance.
# 3) DS/ML guidance (design/evaluation level, not execution/coding) with a clear task type, success signal, data reference, DS lifecycle activity, and no regulated judgments.
# 4) DS roles/specializations & capabilities (design/guidance scope): NLP, CV, Recommenders, Causal/Experimentation, Forecasting/Time-Series, or GenAI/LLM app work.
# 5) DS deliverables (non-executing): EDA report, feature spec, model/evaluation write-up, experiment design/readout, dashboard specification, prototype/API design (not implementation).
# 6) Foundational DS competencies—analysis/guidance only (no coding/ops execution).
# 7) Design work that avoids unsafe access.
# 8) Advice artifacts: advice, plans, rubrics, checklists (not clinical/legal determinations).
# 9) Process intelligence: problem–solution summaries, criteria rationales, plan decisions, user-identification insights (UIA), friction scans, plan fine-tuning.
# 10) Purpose & principles: questions about the system’s purpose/principles or how work fits this platform’s flow.
# 11) Personalization inputs to tailor advice.
# 12) If the user prompt looks like an answer to the prvious encouragement question.

# Always out of scope — return {"proceed": false, "message": "..."}:
# • Non-DS tasks (e.g., physical repair, legal filing).
# • The user expects to provide a plan to enhance skills (execution).
# • Guaranteed outcomes or irreversible actions without review.
# • Unrelated expertise (e.g., chip design, mechanical engineering).
# • Management authority asks (promotion, compensation decisions).
# • Exams/assessments on behalf of a user or impersonation.
# • Hands-on production access or security-sensitive operations without permission.
# • Coding work or code generation.
# • Executing/operating a plan on the user’s behalf.
# • Identity verification or profiling beyond declared consent.

# Helping facts for composing out-of-scope messages:
# Relativity AI’s current product is the User Analysis Agent: it does NOT write or run code or operate systems; it helps you clarify your Data Scientist path by identifying your employment category, prioritizing skills, and surfacing pain points to power a personalized learning plan.

# Special handling
# A) System/about queries (“what is the system / what can you do / what is Relativity AI”):
#    - Return {"proceed": false, "message": "<one-sentence explainer of the system>"}.
#    - Do NOT say “out of scope”; just explain the product in one concise sentence.

# B) Off-track while an encouragement is pending:
#    - If CONTEXT contains a previous encouragement question, and the user’s prompt is out-of-scope, return {"proceed": false, "message": "..."} with TWO parts:
#      1) Boundary + what the agent does (1 short sentence).
#      2) A concise re-ask of the prior encouragement, preserving canonical option labels exactly; you may add “(reply with the exact words)” if options are listed.
# """

PROMPT_CORE = """Role: You are the `Decision Gate` for Relativity AI’s User Analysis Agent. 
Your job is to classify a user's message as in-scope or out-of-scope based on the agent's purpose.

---
[AGENT PURPOSE]
The agent is a Data Science Career Coach & Analyst. 
It helps users understand their data science skills, identify an appropriate role, and get guidance about the data science field.

[IN-SCOPE → return {"proceed": true}]
1. User Analysis: identifying skills, employment category, pain points, or career goals.
2. Data Science Knowledge: any questions about data science fields, roles, concepts, tools, or methods.
3. Small Talk: greetings, thanks, or short social niceties.(e.g., "hi", "how are you", "thanks").
4. Follow-up: a direct answer to the Previous assistant encouragement question.
5. Value/Benefits of DS: questions about the importance, benefits, impact, or reasons to learn data science (e.g., "why is learning data science important?").
6. Specific Information about Data Science Field like Market Capitalization, Job Salaries, etc.

[OUT-OF-SCOPE → return {"proceed": false, "message": "<friendly_message>"}]
1. **Non-Data Science Topics:** Anything unrelated to data science, AI, math, or tech careers. (e.g., "what's the weather", "recipe for lasagna").
2. **Execution of Work:** Asking the agent to *do* the work. (e.g., "write me the code for...", "run this analysis", "debug my script").

---
[OUTPUT CONTRACT]
You MUST return *only* a JSON object in the exact format required. Do not add any other text or markdown.

JSON format
• In scope:
{"proceed": true}

• Out of scope:
{"proceed": false, "message": "<friendly message>"} 

---
[RULES FOR OUT-OF-SCOPE MESSAGES]
1.  The `message` must be friendly, concise, and helpful.
2.  Start by stating the boundary (e.g., "I'm focused on...") and what the agent *does* (e.g., "...helping you with your data science skills and career.").
3.  **If a question exists in Previous assistant encouragement question**: Append a re-ask to guide the user back. If the question lists canonical options, preserve their wording exactly.

---
[SPECIAL HANDLING: "ABOUT" QUESTIONS]
- Trigger only when the user explicitly asks about the assistant/system (e.g., "what can you do?", "who are you?", "what is this system?", "Relativity AI"). Do NOT apply this to questions about data science itself (including the value or importance of learning DS). If both ABOUT and DS knowledge could apply, classify as IN-SCOPE.
- Return this exact JSON:
{"proceed": false, "message": "<2–4 sentence creative, plain-language explainer using the facts below; no questions. If a LAST_ENCOURAGEMENT_QUESTION exists, you MAY append one short final sentence re-asking it (preserve canonical options).>"}

Explainer facts to weave in naturally (use several of these):
- Purpose: Relativity AI builds personalized, intelligence-based learning plans for data science careers.
- Current product focus: the User Analysis Agent (UAA) — it does not write or run code or operate systems.
- What UAA does: clarifies your DS role, maps and prioritizes skills, and surfaces pain points/bottlenecks; captures learning preferences and study modes.
- How inputs are gathered: via auto-inference from your messages and short, targeted surveys; a “segment” = employment category + skills; “insights” = pain points/weaknesses.
- Broader system (for context): after analysis, a Planning Agent designs a tailored plan and an Executing Agent helps carry it out (outside this agent’s scope).
- Principles: plan → design → execute; grounded in learning science (spaced practice, retrieval, interleaving).
- Value: helps you “shift intelligence” — stronger thinking, clearer direction, and an adaptive study approach that goes beyond rote resources.

"""


def _build_gate_prompt(user_message: str, *, prev_enc_question: str | None, prev_survey_type: str | None) -> str:
    ctx_lines = []
    if prev_enc_question:
        ctx_lines.append(f'Previous assistant encouragement: "{prev_enc_question}"')
    # if prev_survey_type:
    #     ctx_lines.append(f"Survey currently shown: {prev_survey_type}")
    ctx_block = "\n".join(ctx_lines) if ctx_lines else "None"

    return f"""{PROMPT_CORE}

CONTEXT:
{ctx_block}

USER PROMPT:
{user_message}
""".strip()


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start:end+1])
        except Exception:
            return {}
    return {}


async def _get_last_assistant_message(
    db: AsyncIOMotorDatabase, *, chat_id: str, user_id: str
) -> Dict[str, Any] | None:
    q = {
        "chat_id": ObjectId(chat_id),
        "user_id": ObjectId(user_id),
        "role": "assistant",
        # exclude out-of-scope
        "$or": [
            {"scope_label": {"$exists": False}},
            {"scope_label": {"$ne": "out_of_scope"}},
        ],
        # must contain something actionable we want the user to respond to
        "$or": [
            {"enc_question": {"$exists": True, "$ne": ""}},
            {"surveyType": {"$exists": True, "$ne": None}},
        ],
    }
    doc = await db["messages"].find_one(
        q,
        sort=[("created_at", -1)],
        projection={"surveyType": 1, "enc_question": 1, "created_at": 1},
    )
    return doc or None


async def component5(
    *,
    db: AsyncIOMotorDatabase,
    chat_id: str,
    user_id: str,
    user_msg: str,
    step,
) -> C05Result:
    """
    Decision Gate with in-flight prompt awareness.
    Returns:
      - {"proceed": true}
      - {"proceed": false, "message": "..."}
    """
    print(" ---------------------------------------------------- ")
    print(f" ----| Starting Component 5 |")

    await step(0.45, "Decision gate (context)")

    # 1) If the user is replying to our last prompt/survey, always proceed.
    last = await _get_last_assistant_message(db, chat_id=chat_id, user_id=user_id)
    prev_enc = (last or {}).get("enc_question") or ""
    print(" ------| Previous encouragement question:", prev_enc)
    prev_survey_type = (last or {}).get("surveyType") or None
    # if prev_enc or prev_survey_type:
    #     # User is answering our question or survey → guaranteed in-scope.
    #     return {"proceed": True}

    # 2) Otherwise use the LLM with context (still robust to short answers)
    await step(0.5, "Decision gate (LLM)")
    prompt = _build_gate_prompt(user_msg, prev_enc_question=prev_enc, prev_survey_type=prev_survey_type)
    # print(prompt)
    try:
        raw = await llm_complete_json(
            prompt=prompt,
            temperature=0.6,
            max_tokens=80,
        )
        data = _extract_json(raw)
        proceed = bool(data.get("proceed"))
        if not proceed:
            msg = (data.get("message") or "").strip()
            if not msg:
                msg = FRIENDLY_FALLBACK
            msg = msg.replace("\n", " ").strip()
            if "?" in msg:
                msg = msg.replace("?", ".")
            return {"proceed": False, "message": msg}
        return {"proceed": True}
    except Exception:
        return {"proceed": False, "message": FRIENDLY_FALLBACK}

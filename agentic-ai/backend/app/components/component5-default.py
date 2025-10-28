# app/components/component5.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional, TypedDict

from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.llm import complete_json as llm_complete_json


class C05Result(TypedDict, total=False):
    proceed: bool
    message: Optional[str]  # present only when proceed == False


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
# • The user expects to provide a plan to enhance skills (execution).
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
# - If the user asks “what is the system / what can you do / what is Relativity AI,” treat it as out-of-scope for downstream components and respond with a single-sentence system explainer per the rule above.

# Style examples (not to be copied verbatim):
# - Coding request → {"proceed": false, "message": "This User Analysis Agent doesn’t write or run code; it clarifies your Data Scientist path by identifying your role, priority skills, and pain points for a personalized learning plan."}
# - Execution/ops → {"proceed": false, "message": "This platform doesn’t execute or operate systems; it analyzes your Data Scientist goals to surface role, skill priorities, and bottlenecks for a tailored learning plan."}
# - System/about → {"proceed": false, "message": "Relativity AI’s current product is a User Analysis Agent that clarifies your Data Scientist role, priority skills, and pain points to drive a personalized learning plan."}
# """

PROMPT_CORE = """
Role: You are the Decision Gate for Relativity AI’s User Analysis Agent. Decide if a user prompt is in scope.
Output contract: Return exactly one JSON object, with no additional text.

JSON format
•	In scope:
{"proceed": true}
•	Out of scope:
{"proceed": false, "message": "<concise statement for the frontend (no questions)>"}
message must be a single, declarative statement (no questions, no requests, no “please”). Keep it concise.  This can explain the reason why it is put of the scope. 

What counts as “in scope”
Set proceed: true if any of the following are true:
1.	Small talk / general niceties that don’t require work products.
Even when in scope, remember this platform is User Analysis Agent only—no planning or executing learning programs, and no coding/production actions.
2.	User Analysis (Data Scientist focus): The prompt is about identifying the Data Scientist role, relevant skills, strengths/weaknesses, pain points, bottlenecks, or transparency about how segments/insights are collected; includes self-assessment, planning, or coaching on alignment, capability gaps, decision stalls, learning loops, bottlenecks, learning modes, onboarding, problem-solving posture, unstuck steps, practice cadence, accountability, constraints, or fear-avoidance.
3.	DS/ML guidance (design/evaluation level, not execution/coding): The prompt fits Data Science and clearly contains:
• a recognized task type (classify, regress, cluster, recommend, summarize, extract, evaluate, forecast),
• a measurable objective/success signal (metric/threshold/acceptance criterion),
• a reference to available data (type/source/format) or a responsible way to obtain it,
• a DS lifecycle activity (problem framing, EDA, feature prep, modeling, evaluation, monitoring),
and does not require regulated professional judgments (medical, legal, financial) as final authority.
4.	DS roles, specializations & capabilities (design/guidance scope): The prompt pertains to NLP (classification, NER, RAG, LLM apps), CV (detection/segmentation/OCR), Recommenders, Causal/Experimentation, Forecasting/Time-Series, or GenAI/LLM app work.
5.	Requested outputs match DS deliverables (non-executing): EDA report, feature list/spec, model/evaluation write-up, experiment design/readout, dashboard specification, or prototype/API design (not implementation).
6.	Foundational DS competencies—analysis/guidance only: Programming & data wrangling, statistics, ML fundamentals, optional deep learning/GenAI, data engineering basics, and MLOps basics as analysis, planning, or guidance (no coding/ops execution).
7.	Design work that avoids unsafe access: The ask is to design workflows, analyses, evaluations, learning plans, or prototypes that do not require privileged/unsafe access or production actions.
8.	Advice artifacts: The desired output is advice, plans, rubrics, or checklists (not clinical/legal determinations).
9.	Process intelligence: Problem-solution summaries, why criteria matter, how plans are decided, user identification insights (UIA), process friction scans, and plan fine-tuning during the DS lifecycle.
10.	Purpose & principles: The prompt concerns the system’s purpose/principles (enhancing thinking, shifting intelligence, helping think outside the box) or how work fits the platform’s flow toward a defined success (insight, plan, design, evaluation), not external execution.
11.	Personalization: The prompt provides (or allows) personalization inputs to tailor advice.

Always out of scope (return proceed: false with a message)
•	The task is not a DS/analytics/ML activity (e.g., physical actions, hardware repair, legal filing).
•	User expects to provide a plan to enhance skills. 
•	The user demands guaranteed outcomes or irreversible actions without review.
•	The task does not fit any listed specialization or requires unrelated expertise (e.g., chip design, mechanical engineering).
•	The user expects management authority (promotion, compensation decisions) rather than DS work products.
•	The prompt requires doing exams/assessments on behalf of a user or impersonation.
•	It demands hands-on production access or security-sensitive operations without proof of permission.
•	The prompt requires coding work 
•	The user expects the agent to perform the plan or execute the plan 
•	The prompt requests identity verification or user profiling beyond declared consent.

Helping Facts that can be used for Reasons for out of scope 
When generating a reason as to why it is out of scope the following information can be used. 

What the relativity AI user analysis agent platform is about, this is only what the application does as a big picture. 
Purpose:
Relativity AI creates personalized, intelligence-based learning plans that help people develop job-specific skills effectively and strategically.
Core Principle:
1.	Plan the problem → 2. Design a personalized plan → 3. Execute the plan.
Personalization Inputs:
•	Learning style and pace
•	Preferred study methods (e.g., projects, code-alongs, quizzes)
•	Depth and medium of learning
How It Works:
Instead of just listing resources, Relativity AI builds a smart, data-driven learning plan:
1.	Profile learner preferences and current skill level.
2.	Design weekly milestones with measurable goals.
3.	Deliver tailored tasks and feedback loops.
4.	Continuously adapt using progress data.
Value:
The system doesn’t just teach skills—it enhances the underlying intelligence that powers skill mastery. Every role (e.g., Backend Developer) requires different intelligence types such as:
•	Problem-solving
•	Technical
•	Collaborative and communication intelligence
Key Goals:
1.	Shift Intelligence Upward – Develop stronger cognitive and analytical abilities, clearer career direction, and an adaptive study approach.
2.	Think Beyond the Box – Elevate IQ-like abilities, not just skill proficiency, so learners can thrive in complex, high-performance environments.
Approach:
•	Integrates proven learning science (spaced practice, retrieval, interleaving).
•	Focuses on both brain development and skill development.
•	Success depends on active participation—Relativity AI guides the plan, but execution lies with the learner.

The agentic ai system is composed of 4 components. 
User analysis agent  -> understanding what employment category, skills and pain points / weaknesses user is experiencing. 
User Planning agent -> based on the results under user analysis agent, the plan is being given to the user develop the required skills. 
User Executing agent -> this is the platform that execute the plan which is being made. 
So the current platform only handles the User analysis agent function. 

User analysis agent helps the user to first discuss the employment category it wants to follow, skills they want to develop and to make the planning effective we need segments and insights which we collect strategically from the user. A segment contains employment category + its related skills and insights are pain points and weaknesses user is experiencing mainly.  We collect them using auto inference method which captures behaviour of the prompts to collect possible segments, insights  and the other method is using the survey method which emits surveys to the users’ interface based on what is given.
"""


FRIENDLY_FALLBACK = (
    "This User Analysis Agent doesn’t write or run code; it clarifies your Data Scientist path by identifying your role, "
    "priority skills, and pain points to drive a personalized learning plan."
)

def _build_gate_prompt(user_message: str) -> str:
    return f"""{PROMPT_CORE}

USER PROMPT:
{user_message}
""".strip()


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    # fast path
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except Exception:
            pass
    # fallback: find outermost braces
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start:end+1])
        except Exception:
            return {}
    return {}


async def component5(
    *,
    db: AsyncIOMotorDatabase,        # reserved for future (not needed today)
    chat_id: str,                    # reserved for telemetry
    user_id: str,                    # reserved for telemetry
    user_msg: str,
    step,
) -> C05Result:
    """
    Decision Gate. Returns:
      - {"proceed": true}
      - {"proceed": false, "message": "..."}
    """
    await step(0.5, "Decision gate (LLM)")

    prompt = _build_gate_prompt(user_msg)
    try:
        raw = await llm_complete_json(
            prompt=prompt,
            temperature=0.6,
            max_tokens=100,
            # system prompt is already set in complete_json to force JSON-only
        )
        data = _extract_json(raw)
        proceed = bool(data.get("proceed"))
        if not proceed:
            msg = (data.get("message") or "").trim() if hasattr(str, "trim") else (data.get("message") or "").strip()
            if not msg:
                msg = FRIENDLY_FALLBACK
            msg = msg.replace("\n", " ").strip()
            if "?" in msg:  # enforce no-questions rule
                msg = msg.replace("?", ".")
            return {"proceed": False, "message": msg}
        return {"proceed": True}
    except Exception:
        # Safe default: block with a clear reason rather than letting pipeline fail ambiguously
        return {
            "proceed": False,
            "message": "Error - This request falls outside the User Analysis Agent’s scope.",
        }

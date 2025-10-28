from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal

from app.db.mongo import get_db
from app.repositories.vault_repo import (
    get_active_vault_version,
    get_vault_by_version,
    list_ec_options,
    list_skill_options_for_ec,
    get_ec_by_id,
    validate_skills_belong_to_ec,
)
from app.repositories.alias_repo import find_ec_by_alias
from app.repositories.chat_repo import get_chat_state, upsert_employment_category, upsert_skills_selection
from app.services.textnorm import normalize
from app.services.intent_llm import detect_intents_llm
from app.services.intent import employment_intent as rb_employment_intent, skills_intent as rb_skills_intent
from app.services.survey import build_ec_survey, build_skills_survey
from app.services.events import emit_event

router = APIRouter(prefix="/uia", tags=["uia"])

# ---------- Request / Response Models ----------

class IntakeRequest(BaseModel):
    chat_id: str
    user_message: str

class IntakeResponse(BaseModel):
    action: Literal["recorded_ec", "show_ec_survey", "show_skills_survey", "none"]
    ec_id: Optional[str] = None
    survey: Optional[dict] = None

class SubmitEmploymentRequest(BaseModel):
    chat_id: str
    employment_category_id: str
    vault_version: str

class SubmitEmploymentResponse(BaseModel):
    # action: Literal["recorded_ec"]
    action: str
    ec_id: str

class SubmitSkillsRequest(BaseModel):
    chat_id: str
    employment_category_id: str
    vault_version: str
    let_system_decide: bool = False
    skills_selected: Optional[List[str]] = Field(default=None)

    @validator("skills_selected", always=True)
    def validate_selection(cls, v, values):
        # Enforce mutual exclusivity at the DTO level (server will also re-check)
        if values.get("let_system_decide"):
            return None
        return v

class SubmitSkillsResponse(BaseModel):
    action: Literal["recorded_skills"]
    mode: Literal["manual", "system_decide"]
    skills_count: int

# ---------- Helpers ----------

async def _active_version_or_404(db) -> str:
    version = await get_active_vault_version(db)
    if not version:
        raise HTTPException(status_code=404, detail="No active vault")
    return version

async def _ensure_version_current(db, provided_version: str) -> str:
    current = await _active_version_or_404(db)
    if provided_version != current:
        # Stale or wrong version
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Vault version changed. Please refresh the survey.")
    return current

def _skills_already_recorded(chat_state: Optional[dict]) -> bool:
    if not chat_state:
        return False
    if chat_state.get("let_system_decide") is True:
        return True
    skills = chat_state.get("skills_selected") or []
    return len(skills) > 0

# ---------- Routes ----------

@router.post("/intake", response_model=IntakeResponse)
async def intake(req: IntakeRequest):
    db = get_db()

    # Load active vault
    version = await _active_version_or_404(db)
    print(" ------| Using Segment vault version:", version)

    # Normalize & detect intents (LLM first, fallback to rule-based)
    tnorm = normalize(req.user_message)
    try:
        emp_int, skl_int, ec_hit = await detect_intents_llm(req.user_message)
        await emit_event("IntentDetectedLLM", req.chat_id, {"employment_intent": emp_int, "skills_intent": skl_int, "ec_hit": ec_hit})
        print(f" ------| LLM intents captured: emp={emp_int} | skl={skl_int} | ec_hit={ec_hit}")
    except Exception:
        # Fallback: lightweight rule-based detection
        emp_int = rb_employment_intent(req.user_message)
        skl_int = rb_skills_intent(req.user_message)
        # ec_hit = await find_ec_by_alias(db, version, tnorm)
        ec_hit = None
        await emit_event("IntentDetectedFallback", req.chat_id, {"employment_intent": emp_int, "skills_intent": skl_int})
        print(f" ------| Rule-based intents: emp={emp_int} | skl={skl_int} | ec_hit={ec_hit}")

    chat_state = await get_chat_state(db, req.chat_id)
    ec_current = chat_state.get("employment_category_id") if chat_state else None
    print(" ------| Current EC in chat state:", ec_current)
    skills_done = _skills_already_recorded(chat_state)
    print(" ------| Skills already recorded in chat state:", skills_done)

    options = await list_ec_options(db, version)
    print(" ------| Employment categories available in vault:", [o["label"] for o in options])
    opts = await list_skill_options_for_ec(db, version, "ec_ds")
    print(" ------| Skills available for EC 'ec_ds':", [o["label"] for o in opts])

    # New rule 1: DO NOT update EC if chat already has one
    if ec_hit == "ec_ds":
        if not ec_current:
            # First-time EC set allowed
            await upsert_employment_category(db, req.chat_id, "ec_ds", version)
            print(f" ------| Recoreded EC {ec_hit} for the first time")

            if skl_int and not skills_done:
                opts = await list_skill_options_for_ec(db, version, "ec_ds")
                if not opts:
                    return IntakeResponse(action="recorded_ec", ec_id="ec_ds")
                
                await emit_event("SkillsSurveyShown", req.chat_id, {"option_count": len(opts)}, version)
                print(f" ------| Creating skills survey for EC 'ec_ds' with {len(opts)} options")

                return IntakeResponse(action="show_skills_survey", survey=build_skills_survey(opts, version, "ec_ds"))
            return IntakeResponse(action="recorded_ec", ec_id="ec_ds")
        else:
            # EC already set → do not overwrite
            if skl_int and not skills_done:
                # If user is asking about skills and hasn't filled them, show skills survey for the existing EC
                opts = await list_skill_options_for_ec(db, version, ec_current)
                if opts:
                    await emit_event("SkillsSurveyShown", req.chat_id, {"option_count": len(opts)}, version)
                    print(f" ------| Creating skills survey for existing EC '{ec_current}' with {len(opts)} options")

                    return IntakeResponse(action="show_skills_survey", survey=build_skills_survey(opts, version, ec_current))
            return IntakeResponse(action="none")

    # Employment implied but no EC set yet → EC survey
    if emp_int and not ec_current:
        options = await list_ec_options(db, version)
        if not options:
            raise HTTPException(500, "Vault has no employment categories")
        await emit_event("ECSurveyShown", req.chat_id, {"option_count": len(options)}, version)
        print(f" ------| Creating EC survey with {len(options)} options")

        return IntakeResponse(action="show_ec_survey", survey=build_ec_survey(options, version))

    # Skills flow
    if skl_int:
        if not ec_current:
            # Need EC first
            options = await list_ec_options(db, version)
            await emit_event("ECSurveyShown", req.chat_id, {"option_count": len(options)}, version)
            print(f" ------| Creating EC survey with {len(options)} options before skills")

            return IntakeResponse(action="show_ec_survey", survey=build_ec_survey(options, version))
        # New rule 2: if skills already recorded, do NOT show survey again
        if not skills_done:
            opts = await list_skill_options_for_ec(db, version, ec_current)
            if opts:
                await emit_event("SkillsSurveyShown", req.chat_id, {"option_count": len(opts)}, version)
                print(f" ------| Creating skills survey for existing EC '{ec_current}' with {len(opts)} options")

                return IntakeResponse(action="show_skills_survey", survey=build_skills_survey(opts, version, ec_current))
        return IntakeResponse(action="none")

    print(" ------| No action taken for compoentnt 6")
    return IntakeResponse(action="none")

@router.post("/submit/employment", response_model=SubmitEmploymentResponse)
async def submit_employment(req: SubmitEmploymentRequest):
    db = get_db()
    await _ensure_version_current(db, req.vault_version)

    print(" ------| Submitting EC:", req.employment_category_id, "for chat:", req.chat_id)

    # New rule 1 (server-side): if EC already exists, do NOT allow update
    chat = await get_chat_state(db, req.chat_id)
    if chat and chat.get("employment_category_id"):
        raise HTTPException(status_code=409, detail="Employment category already set for this chat; updates are not allowed.")

    # Validate EC exists in vault
    ec = await get_ec_by_id(db, req.vault_version, req.employment_category_id)
    if not ec:
        raise HTTPException(status_code=400, detail="Invalid employment category")

    await upsert_employment_category(db, req.chat_id, req.employment_category_id, req.vault_version)
    print(" ------| Employment category recorded.")

    if req.employment_category_id == "ec_ds":
        emp_cat = "Data Scientist"

    text = f"Awesome your employment category is set to **{emp_cat}**, next Which skills do you want to build next?"

    # return SubmitEmploymentResponse(action="recorded_ec", ec_id=req.employment_category_id)
    return SubmitEmploymentResponse(action=text, ec_id=req.employment_category_id)

@router.post("/submit/skills", response_model=SubmitSkillsResponse)
async def submit_skills(req: SubmitSkillsRequest):
    db = get_db()
    await _ensure_version_current(db, req.vault_version)

    print(" ------| Submitting skills for EC:", req.employment_category_id, "for chat:", req.chat_id, "let_system_decide:", req.let_system_decide, "skills_selected:", req.skills_selected)

    # EC must exist in vault
    ec = await get_ec_by_id(db, req.vault_version, req.employment_category_id)
    if not ec:
        raise HTTPException(status_code=400, detail="Invalid employment category")

    # Chat EC must match (or be empty → allow first set via employment submit only)
    chat = await get_chat_state(db, req.chat_id)
    chat_ec = chat.get("employment_category_id") if chat else None
    if chat_ec and chat_ec != req.employment_category_id:
        raise HTTPException(status_code=400, detail="Employment category mismatch with chat state. Refresh and choose skills again.")

    # New rule 2 (server-side): if skills already recorded, do NOT allow re-submit
    if _skills_already_recorded(chat):
        raise HTTPException(status_code=409, detail="Skills already recorded for this chat; updates are not allowed.")

    if req.let_system_decide:
        await upsert_skills_selection(db, req.chat_id, req.employment_category_id, None, True, req.vault_version)
        return SubmitSkillsResponse(action="recorded_skills", mode="system_decide", skills_count=0)

    if not req.skills_selected or not (1 <= len(req.skills_selected) <= 4):
        raise HTTPException(status_code=400, detail="Pick between 1 and 4 skills.")

    ok = await validate_skills_belong_to_ec(db, req.vault_version, req.employment_category_id, req.skills_selected)
    if not ok:
        raise HTTPException(status_code=400, detail="One or more skills do not belong to the selected employment category.")

    await upsert_skills_selection(db, req.chat_id, req.employment_category_id, req.skills_selected, False, req.vault_version)
    print(" ------| Skills selection recorded.")
    
    return SubmitSkillsResponse(action="recorded_skills", mode="manual", skills_count=len(req.skills_selected))
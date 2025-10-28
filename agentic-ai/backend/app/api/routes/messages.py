from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Callable, Optional, Dict, Any
import json, asyncio
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.db.mongo import get_db
from app.api.deps import get_current_user
from app.core.security import decode_token
from app.services.progress import broker
from app.repositories.chats_repo import verify_chat_owner, touch_chat_activity
from app.repositories.chat_repo import get_chat_state
from app.repositories.messages_repo import list_messages as repo_list, insert_message
from app.repositories.vault_repo import get_active_vault_version
from app.api.routes.uia import intake as uia_intake_route, IntakeRequest
from app.services.insight_engine import stage01_auto_infer
from app.services.insight_survey import build_surveys
from app.components.component10 import component10
from app.components.component5 import component5, _get_last_assistant_message
from app.rag.scripts.component8_rag import component8_rag_answer

router = APIRouter(prefix="/messages", tags=["messages"])

# ------------------ Helper functions ------------------

def _bsonify(obj):
    # Convert Pydantic models (and any nested structures) to plain JSON-like values
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, (list, tuple)):
        return [_bsonify(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _bsonify(v) for k, v in obj.items()}
    return obj  # primitives pass through

def make_stepper(rid: Optional[str]) -> Callable[[int, str], Any]:
    """
    Returns an async function step(index:int, label:str) that publishes SSE progress.
    If rid is None, it's a no-op (safe to call).
    """
    async def step(index: int, label: str):
        if rid:
            await broker.publish(rid, {"type": "step", "label": label})
    return step

def _skills_already_recorded(chat_state: Optional[dict]) -> bool:
    if not chat_state:
        return False
    if chat_state.get("let_system_decide") is True:
        return True
    skills = chat_state.get("skills_selected") or []
    return len(skills) > 0

async def component6(
    db,
    *,
    chat_id: str,
    user_id: str,
    prompt: str,
    step: Callable[[int, str], Any],
) -> Dict[str, Any]:
    
    print("=="*30);print(f" ----| Starting Component 6 |")

    # C06 steps (1..5) — keep indices aligned with your timeline
    _version = await get_active_vault_version(db)

    chat_state = await get_chat_state(db, chat_id)
    ec_current: Optional[str] = chat_state.get("employment_category_id") if chat_state else None
    skills_done: bool = _skills_already_recorded(chat_state)

    # If both EC and skills are done, skip C06 surveys
    if ec_current and skills_done:
        print(" ----| Component 6 done | skipping surveys (EC and skills already recorded) |")
        return {
            "uia_action": "none",
            "surveyType": None,
        }

    await step(1, "Detecting intent (LLM)")
    uia_resp = await uia_intake_route(IntakeRequest(chat_id=chat_id, user_message=prompt))

    if uia_resp.action in ("show_ec_survey", "show_skills_survey") and uia_resp.survey:
        await step(2, "Building the Surveys")

        if uia_resp.action == "show_ec_survey":
            surveyType = "ec_survey"
        else:
            surveyType = "skills_survey"

        return {
            "uia_action": uia_resp.action,
            "survey_type": surveyType,
            "survey": uia_resp.survey,
        }

    return {
        "uia_action": uia_resp.action,
        "surveyType": None,
    }

async def component7(
    db,
    *,
    chat_id: str,
    user_id: str,
    prompt: str,
    step: Callable[[int, str], Any],
) -> Dict[str, Any]:

    print("=="*30);print(f" ----| Starting Component 7 |")

    # Stage-01 (keep as-is; we still allow auto-inference/batch-expansion to run)
    await step(3, "Insights: Stage-01 starting")
    print("### Stage 1: Auto Inference")
    result = await stage01_auto_infer(db, chatId=chat_id, user_text=prompt)

    auto_taken = int(result.get("autoTakenCount", 0))
    question_only = int(result.get("questionOnlyCount", 0))
    touched = result.get("touchedBatchIds", []) or []
    pending_map = result.get("pendingByBatch", {}) or {}
    pending_total = sum(len(v) for v in pending_map.values())

    # Read prereqs from C06 state
    chat_state = await get_chat_state(db, chat_id)
    ec_current: Optional[str] = chat_state.get("employment_category_id") if chat_state else None
    skills_done: bool = _skills_already_recorded(chat_state)

    # Gate: only build Insight surveys when EC exists AND skills are done
    if not ec_current or not skills_done:
        await step(5, "Insights: Skipping surveys (requires employment category & skills).")
        return {
            "autoTakenCount": auto_taken,
            "questionOnlyCount": question_only,
            "touchedBatchIds": touched,
            "pendingByBatch": pending_map,
            "surveysPrepared": 0,
            "survey_type": "insight_survey",
            "survey": None,
            "skipReason": "prereqs_not_met",
            "prereqs": {
                "employmentCategory": bool(ec_current),
                "skills": bool(skills_done),
            },
        }

    print()
    print("### Stage 2: Building surveys (if any pending)")
    surveys = await build_surveys(db, chatId=chat_id)
    batches = surveys.batches or []
    batch_count = len(batches)

    if batch_count > 0:
        q_count = sum(len(b.questions) for b in batches)  # count questions across batches
        await step(5, f"Insights: Follow-up surveys ready ({q_count} question(s)) in {batch_count} batch(es)")
    else:
        await step(5, "Insights: No follow-ups needed right now")

    return {
        "autoTakenCount": auto_taken,
        "questionOnlyCount": question_only,
        "touchedBatchIds": touched,
        "pendingByBatch": pending_map,
        "surveysPrepared": batch_count,
        "survey_type": "insight_survey",
        "survey": _bsonify(surveys),
    }


# ------------------ Message listing and sending ------------------

@router.get("/{chat_id}")
async def list_messages(chat_id: str, user=Depends(get_current_user)):
    db = get_db()
    if not await verify_chat_owner(db, user["id"], chat_id):
        raise HTTPException(404, "Chat not found")
    return await repo_list(db, user["id"], chat_id)

class SendReq(BaseModel):
    prompt: str
    request_id: Optional[str] = None  # for progress tracking

@router.post("/{chat_id}")
async def send(chat_id: str, payload: SendReq, user=Depends(get_current_user)):
    db = get_db()
    if not await verify_chat_owner(db, user["id"], chat_id):
        raise HTTPException(404, "Chat not found")
    
    print("=="*30);print(f" --| New message in chat {chat_id} from user {user['id']}: {payload.prompt[:50]}...")
    print()

    rid = payload.request_id or None
    step = make_stepper(rid)

    try:
        # 0) Save user message (outside C06)
        await step(0, "Queuing request")
        await insert_message(db, user["id"], chat_id, "user", content=payload.prompt)

        # ---- Component 05 (Decision Gate) ----
        c05 = await component5(
            db=db,
            chat_id=chat_id,
            user_id=user["id"],
            user_msg=payload.prompt,
            step=step,
        )
        print("=="*30)
        # print(f" ----| Component 5 result: {c05}")

        if not c05.get("proceed", False):
            # Build a simple assistant response: content only
            assistant_msg = {
                "role": "assistant",
                "type": "text",
                "content": c05.get("message") or "This request falls outside the User Analysis Agent’s scope.",
                "surveyType": None,
                "survey": None,
                "enc_question": "",
            }

            await insert_message(
                db,
                user_id=user["id"],
                chat_id=chat_id,
                role="assistant",
                content=assistant_msg["content"],
                type="text",
                survey_type=None,
                survey=None,
                enc_question="",
                scope_label="out_of_scope",
            )

            await broker.publish(rid, {"type": "done"})
            return assistant_msg

        # ---- Component 06 (UIA) ----
        c06 = await component6(
            db,
            chat_id=chat_id,
            user_id=user["id"],
            prompt=payload.prompt,
            step=step,
        )
        print("=="*30)
        # print(f" ----| Component 6 result: {c06}")

        # await touch_chat_activity(db, chat_id)

        # ---- Component 07 (Insights) ----
        c07 = await component7(
            db,
            chat_id=chat_id,
            user_id=user["id"],
            prompt=payload.prompt,
            step=step,
        )
        print("=="*30)
        # print(f" ----| Component 7 result: {c07}")

        # ---- Component 08 (RAG) ----
        chat_state = await get_chat_state(db, chat_id)
        ec_current: Optional[str] = chat_state.get("employment_category_id") if chat_state else None
        last = await _get_last_assistant_message(db, chat_id=chat_id, user_id=user["id"])
        prev_enc = (last or {}).get("enc_question") or ""

        c08 = None
        try:
            c08 = await component8_rag_answer(user_question=payload.prompt, prev_enc=prev_enc, step=step)
        except Exception as e:
            print("Component 8 (RAG) error:", e)
        # print("=="*30);print(f" ----| Component 8 result: {c08}")

        # ---- Component 10 (Encouragement Question) ----
        c10 = await component10(
            db,
            chat_id=chat_id,
            user_id=user["id"],
            user_msg=payload.prompt,
            c06=c06,
            c07=c07,
            step=step,
        )
        print("=="*30)
        # print(f" ----| Component 10 result: {c10}")


        # ---------------- Build final assistant message ----------------
        # Choose survey if any (one survey at a time)
        survey_type: str | None = None
        survey_obj: dict | None = None

        # C06 survey takes precedence (EC or Skills)
        if c06.get("survey") and c06.get("survey_type"):
            survey_type = c06["survey_type"]
            survey_obj = c06["survey"]
        # Otherwise, C07 insight survey (only if prepared)
        elif c07.get("surveysPrepared", 0) > 0 and c07.get("survey"):
            survey_type = c07.get("survey_type") or "insight_survey"
            survey_obj = c07["survey"]

        # Encouragement question only if we're NOT sending a survey now
        enc_q: str = ""
        
        if c10 and c10.get("stage") != "none" and c10.get("question"):
            enc_q = c10["question"]

        if c10 and c10.get("stage") == "none":
            qFull = "All the insights have been gathered. No further questions at this time. Now you can proceed to planning if you wish to!"
            enc_q = qFull


        content_text = ""
        rag_srcs: list = []

        if c08 and c08.get("used") and c08.get("answer_md"):
            content_text = c08["answer_md"]
            rag_srcs = c08.get("sources") or [] 

        assistant_msg = {
            "id": "",
            "role": "assistant",
            "content": content_text,
            "surveyType": survey_type,
            "survey": survey_obj,
            "enc_question": enc_q,
            "sources": rag_srcs,
        }

        # Save assistant message
        msgId = await insert_message(
                db,
                user_id=user["id"],
                chat_id=chat_id,
                role="assistant",
                content=assistant_msg["content"],
                type="text" if survey_type is None else "survey",
                survey_type=assistant_msg["surveyType"],
                survey=assistant_msg["survey"],
                enc_question=assistant_msg["enc_question"],
                sources=assistant_msg["sources"],
            )

        assistant_msg = {
            "id": msgId,
            "role": "assistant",
            "content": content_text,
            "surveyType": survey_type,
            "survey": survey_obj,
            "enc_question": enc_q,
            "sources": rag_srcs,
        }

        await broker.publish(rid, {"type": "done"})

        print("=="*30);print(" --| Message processing complete |")
        # print(" --| Assistant message:\n", json.dumps(assistant_msg, indent=2) )
        print("====================================================")
        
        return assistant_msg

    except Exception as e:
        # surface an SSE error event for the loader
        await broker.publish(rid, {"type": "error", "message": "Processing failed"})
        raise

@router.get("/{chat_id}/progress")
async def stream_progress(chat_id: str, request: Request, request_id: str, access_token: str):
    """
    SSE: /messages/{chat_id}/progress?request_id=...&access_token=...
    """
    db = get_db()
    # validate token
    try:
        payload = decode_token(access_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid access token")
    user_id = payload.get("sub")
    if not await verify_chat_owner(db, user_id, chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")

    queue = broker.get_queue(request_id)

    async def event_gen():
        # Initial no-op to open stream
        yield "event: open\ndata: {}\n\n"
        try:
            while True:
                # Allow heartbeats to keep connection alive
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    # Comment line = SSE heartbeat
                    yield ": keep-alive\n\n"
                    continue

                payload = json.dumps(evt)
                yield f"data: {payload}\n\n"

                if evt.get("type") in ("done", "error"):
                    break
        finally:
            broker.close(request_id)

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # for some proxies
    }
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
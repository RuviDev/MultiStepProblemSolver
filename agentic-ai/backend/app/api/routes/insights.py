# app/api/routes/insights.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.api.deps import get_current_user
from app.db.mongo import get_db
from app.services.insight_engine import stage01_auto_infer
from app.services.insight_survey import build_surveys, submit_survey
from app.models.insights import SurveySubmission
from app.repositories.chats_repo import verify_chat_owner
from app.repositories.messages_repo import update_insight_survey_message_with_submission_by_id

router = APIRouter(prefix="/insights", tags=["insights"])


class AutoInferRequest(BaseModel):
    chatId: str
    text: str


@router.get("/_health")
async def health():
    return {"status": "ok"}


@router.post("/auto-infer")
async def insights_auto_infer(
    req: AutoInferRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Stage-01: run auto-inference → thresholds → batch expansion.
    Response includes pendingByBatch, insightStats, touchedBatchIds.
    """
    print("---------------------Auto-infer request:", req)
    result = await stage01_auto_infer(db, chatId=req.chatId, user_text=req.text)
    return result


@router.get("/pending/{chat_id}")
async def insights_pending(
    chat_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Stage-02: build per-batch micro-surveys for this chat (if any pending).
    """
    payloads = await build_surveys(db, chatId=chat_id)
    return payloads


@router.post("/submit")
async def insights_submit(
    submission: SurveySubmission,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(get_current_user),
):
    """
    Stage-02: submit survey responses. Survey wins (overrides Stage-01 if conflicts).
    Returns updated insightStats.
    """
    db = get_db()
    if not await verify_chat_owner(db, user["id"], submission.chatId):
        raise HTTPException(404, "Chat not found")
    print(submission)
    try:
        stats = await submit_survey(db, submission=submission)
        print(submission)

        ok = await update_insight_survey_message_with_submission_by_id(
            db,
            user_id=user["id"],
            chat_id=submission.chatId,
            msg_id=submission.msgId,
            batch_id=submission.batchId,
            submission={
                "responses": [
                    (r.model_dump() if hasattr(r, "model_dump") else dict(r))
                    for r in submission.responses
                ],
                "submittedAt": submission.submittedAt.isoformat() if hasattr(submission, "submittedAt") else body.submittedAt,
            },
    )
        print(f"Updated insight survey submission for chat {submission.chatId}, batch {submission.batchId}: {ok}")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": ok, "insightStats": stats.model_dump()}

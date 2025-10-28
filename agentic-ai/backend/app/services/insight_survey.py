# app/services/insight_survey.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.settings import settings
from app.repositories.insight_vault_repo import InsightVaultRepo
from app.repositories.chat_insights_repo import ChatInsightsRepo
from app.models.insights import (
    SurveyPayload,
    SurveyQuestion,
    SurveyQuestionOption,
    SurveySubmission,
    InsightStats,
    InsightSurveyEnvelope,
)


async def build_surveys(
    db: AsyncIOMotorDatabase,
    *,
    chatId: str,
) -> InsightSurveyEnvelope:
    """
    Build the "insight survey" envelope.
   - One SurveyPayload per touched batch that still has {taken: null} rows.
   - Ordering: question_only first, then batch_fill, tie-break by higher confidence.
    """

    print(f" ------| Building surveys for chatId={chatId}")

    vault_repo = InsightVaultRepo(db)
    pcch_repo = ChatInsightsRepo(db)
    vaultVersion = settings.INSIGHT_VAULT_VERSION

    session = await pcch_repo.get_session(chatId)
    if not session:
        return InsightSurveyEnvelope(
           vaultVersion=None, language="en", batches=[]
        )

    touched = (session.get("touchedBatchIds") or [])
    if not touched:
        return InsightSurveyEnvelope(
           vaultVersion=vaultVersion, language="en", batches=[]
        )
    print(f" ------| Touched batches: {touched}")

    pending_map = await pcch_repo.list_pending_by_batch(chatId, touched)
    if not pending_map:
        return InsightSurveyEnvelope(
           vaultVersion=vaultVersion, language="en", batches=[]
        )
    print(f" ------| Pending map keys: {list(pending_map.keys())}")

    payloads: List[SurveyPayload] = []

    for batchId, pending_list in pending_map.items():
        # load batch for titles + insight definitions
        batch = await vault_repo.get_batch(batchId)
        if not batch:
            continue

        # build lookup for insights
        ins_by_id = {ins.insightId: ins for ins in batch.insights if ins.isActive}

        # order as required
        ordered = sorted(
            pending_list,
            key=lambda r: (0 if (r.get("pendingReason") == "question_only") else 1, -float(r.get("confidence", 0.0))),
        )

        questions: List[SurveyQuestion] = []
        for row in ordered:
            iid = row["insightId"]
            ins = ins_by_id.get(iid)
            if not ins:
                continue

            q_type = "multi" if ins.isMultiSelect else "single"
            options = [
                SurveyQuestionOption(answerId=aid, label=ans.text)
                for aid, ans in ins.answers.items()
            ]

            questions.append(
                SurveyQuestion(
                    insightId=ins.insightId,
                    uiQuestion=ins.question,
                    type=q_type,  # single | multi
                    options=options,
                    includeOther=True,
                    noteOtherLabel="Other (write-in)",
                )
            )

        if not questions:
            continue

        payloads.append(
            SurveyPayload(
                batchId=batch.batchId,
                title=f"{batch.name} (Follow-up)",
                language=batch.language or "en",
                questions=questions,
                ordering="question_only_first",
            )
        )

    return InsightSurveyEnvelope(
       surveyType="insight",
       vaultVersion=vaultVersion,
       language="en",
       batches=payloads,
   )


async def submit_survey(
    db: AsyncIOMotorDatabase,
    *,
    submission: SurveySubmission,
) -> InsightStats:
    """
    Validate and write survey results (survey wins). Recompute stats and return.
    """
    vault_repo = InsightVaultRepo(db)
    pcch_repo = ChatInsightsRepo(db)
    vaultVersion = submission.submittedAt and submission.submittedAt.isoformat()  # not strictly needed

    # load the batch for validation
    batch = await vault_repo.get_batch(submission.batchId)
    if not batch:
        raise ValueError("Unknown batchId")

    # build insight map for validation
    insight_map = {i.insightId: i for i in batch.insights if i.isActive}

    for resp in submission.responses:
        ins = insight_map.get(resp.insightId)
        if not ins:
            raise ValueError(f"insightId '{resp.insightId}' not in batch '{batch.batchId}'")

        if ins.isMultiSelect:
            if not resp.answerIds or not isinstance(resp.answerIds, list):
                raise ValueError(f"insightId '{ins.insightId}' expects multiple answers")
            # validate each answerId
            for aid in resp.answerIds:
                if aid not in ins.answers:
                    raise ValueError(f"Invalid answerId '{aid}' for insight '{ins.insightId}'")
            # write
            await pcch_repo.write_survey_multi(
                chatId=submission.chatId,
                batchId=batch.batchId,
                insightId=ins.insightId,
                answerIds=resp.answerIds,
                vaultVersion=batch.vaultVersion,
            )
        else:
            if not resp.answerId or resp.answerId not in ins.answers:
                raise ValueError(f"Invalid or missing answerId for insight '{ins.insightId}'")
            await pcch_repo.write_survey_single(
                chatId=submission.chatId,
                batchId=batch.batchId,
                insightId=ins.insightId,
                answerId=resp.answerId,
                vaultVersion=batch.vaultVersion,
            )

    # Stats after all writes
    stats = await pcch_repo.recompute_stats(submission.chatId)
    return stats

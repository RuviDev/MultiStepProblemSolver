# app/repositories/chat_insights_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Set, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne

from app.db.init_db import CHAT_INSIGHT_SESSIONS, CHAT_INSIGHT_STATES
from app.models.insights import InsightStats


class ChatInsightsRepo:
    """
    Per-Chat Conversation History (PCCH) repo for Component 07:
      - chat_insight_sessions (one per chat)
      - chat_insight_states (one per {chatId, insightId})
    Idempotent upserts throughout.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.sessions = db[CHAT_INSIGHT_SESSIONS]
        self.states = db[CHAT_INSIGHT_STATES]

    # Only write if the row is not yet taken (covers survey OR prior auto-inference)
    def _only_if_not_taken(self, chatId: str, insightId: str) -> dict:
        return {
            "chatId": chatId,
            "insightId": insightId,
            "taken": {"$ne": True},  # match docs where taken is null/missing/False
        }

    # ---------- Sessions ----------

    async def ensure_session(self, chatId: str, vaultVersion: str) -> None:
        now = datetime.utcnow()
        await self.sessions.update_one(
            {"chatId": chatId},
            {
                "$setOnInsert": {
                    "chatId": chatId,
                    "touchedBatchIds": [],
                    "insightStats": {"takenCount": 0, "pendingCount": 0},
                    # "vaultVersion": vaultVersion,
                    "createdAt": now,
                },
                # "$set": {"updatedAt": now, "vaultVersion": vaultVersion},
                "$set": {"updatedAt": now},
            },
            upsert=True,
        )

    async def union_touch_batch(self, chatId: str, batchId: str) -> None:
        now = datetime.utcnow()
        await self.sessions.update_one(
            {"chatId": chatId},
            {"$addToSet": {"touchedBatchIds": batchId}, "$set": {"updatedAt": now}},
            upsert=True,
        )

    async def get_session(self, chatId: str) -> Optional[Dict]:
        return await self.sessions.find_one({"chatId": chatId})

    async def recompute_stats(self, chatId: str) -> InsightStats:
        takenCount = await self.states.count_documents({"chatId": chatId, "taken": True})
        pendingCount = await self.states.count_documents({"chatId": chatId, "taken": None})
        stats = {"takenCount": takenCount, "pendingCount": pendingCount}
        await self.sessions.update_one({"chatId": chatId}, {"$set": {"insightStats": stats}})
        return InsightStats(**stats)

    # ---------- Read taken/pending sets ----------

    async def get_taken_and_pending(self, chatId: str) -> Tuple[Set[str], Set[str]]:
        taken_ids: Set[str] = set()
        pending_ids: Set[str] = set()

        async for doc in self.states.find({"chatId": chatId}, projection={"insightId": 1, "taken": 1}):
            if doc.get("taken") is True:
                taken_ids.add(doc["insightId"])
            elif doc.get("taken") is None:
                pending_ids.add(doc["insightId"])
        return taken_ids, pending_ids

    # ---------- Stage-01 writes ----------

    async def write_auto_take_single(
        self,
        *,
        chatId: str,
        batchId: str,
        insightId: str,
        answerId: str,
        mode: str,  # "qa" | "answer_only"
        confidence: float,
        evidence: List[str],
        vaultVersion: str,
    ) -> None:
        now = datetime.utcnow()
        await self.states.update_one(
            {"chatId": chatId, "insightId": insightId},
            # self._only_if_not_taken(chatId, insightId),
            {
                "$set": {
                    "chatId": chatId,
                    "batchId": batchId,
                    "insightId": insightId,
                    "taken": True,
                    "answerId": answerId,
                    "answerIds": None,
                    "pendingReason": None,
                    "takenMeta": {
                        "source": "auto-inference",
                        "mode": mode,
                        "confidence": float(confidence),
                        "evidence": list(evidence),
                        "vaultVersion": vaultVersion,
                    },
                    "updatedAt": now,
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )

    async def write_auto_take_multi(
        self,
        *,
        chatId: str,
        batchId: str,
        insightId: str,
        answerIds: List[str],
        mode: str,  # "qa" | "answer_only"
        confidence: float,
        evidence: List[str],
        vaultVersion: str,
    ) -> None:
        now = datetime.utcnow()
        await self.states.update_one(
            {"chatId": chatId, "insightId": insightId},
            {
                "$set": {
                    "chatId": chatId,
                    "batchId": batchId,
                    "insightId": insightId,
                    "taken": True,
                    "answerId": None,
                    "answerIds": list(answerIds),
                    "pendingReason": None,
                    "takenMeta": {
                        "source": "auto-inference",
                        "mode": mode,
                        "confidence": float(confidence),
                        "evidence": list(evidence),
                        "vaultVersion": vaultVersion,
                    },
                    "updatedAt": datetime.utcnow(),
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )

    async def write_question_only(
        self,
        *,
        chatId: str,
        batchId: str,
        insightId: str,
        confidence: float,
        evidence: List[str],
        vaultVersion: str,
    ) -> None:
        now = datetime.utcnow()
        await self.states.update_one(
            {"chatId": chatId, "insightId": insightId},
            # self._only_if_not_taken(chatId, insightId),
            {
                "$set": {
                    "chatId": chatId,
                    "batchId": batchId,
                    "insightId": insightId,
                    "taken": None,
                    "answerId": None,
                    "answerIds": None,
                    "pendingReason": "question_only",
                    "takenMeta": {
                        "source": "auto-inference",
                        "mode": None,
                        "confidence": float(confidence),
                        "evidence": list(evidence),
                        "vaultVersion": vaultVersion,
                    },
                    "updatedAt": now,
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )

    # ---------- Batch Expansion (MUST) ----------

    async def batch_expand_pending(
        self,
        *,
        chatId: str,
        batchId: str,
        candidateInsightIds: Iterable[str],
        vaultVersion: str,
    ) -> int:
        """
        For all *active* insights in the touched batch, create pending rows for any that
        do not already exist as taken or pending.
        Returns the number of inserted pending rows.
        """
        existing: Set[str] = set()
        async for s in self.states.find(
            {"chatId": chatId, "batchId": batchId},
            projection={"insightId": 1},
        ):
            existing.add(s["insightId"])

        to_insert = [iid for iid in candidateInsightIds if iid not in existing]
        if not to_insert:
            return 0

        now = datetime.utcnow()
        ops = []
        for iid in to_insert:
            ops.append(
                UpdateOne(
                    {"chatId": chatId, "insightId": iid},
                    {
                        "$setOnInsert": {
                            "chatId": chatId,
                            "batchId": batchId,
                            "insightId": iid,
                            "taken": None,
                            "answerId": None,
                            "answerIds": None,
                            "pendingReason": "batch_fill",
                            "takenMeta": {
                                "source": "batch-expansion",
                                "mode": None,
                                "confidence": 1.0,
                                "evidence": [],
                                "vaultVersion": vaultVersion,
                            },
                            "createdAt": now,
                            "updatedAt": now,
                        }
                    },
                    upsert=True,
                )
            )

        if ops:
            res = await self.states.bulk_write(ops, ordered=False)
            return (res.upserted_count or 0)
        return 0

    # ---------- Pending (for Stage-02) ----------

    async def list_pending_by_batch(
        self, chatId: str, touchedBatchIds: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Return { batchId: [ {insightId, pendingReason, confidence}, ... ] } for all pending rows.
        If touchedBatchIds is provided, restrict to those batches.
        """
        q: Dict = {"chatId": chatId, "taken": None}
        if touchedBatchIds:
            q["batchId"] = {"$in": list(touchedBatchIds)}

        out: Dict[str, List[Dict]] = {}
        cur = self.states.find(q, projection={"batchId": 1, "insightId": 1, "pendingReason": 1, "takenMeta": 1})
        async for row in cur:
            b = row["batchId"]
            out.setdefault(b, []).append(
                {
                    "insightId": row["insightId"],
                    "pendingReason": row.get("pendingReason"),
                    "confidence": float(row.get("takenMeta", {}).get("confidence", 0.0)),
                }
            )
        return out

    # ---------- Insight Surveys (for Stage-02) ----------
    async def write_survey_single(
        self,
        *,
        chatId: str,
        batchId: str,
        insightId: str,
        answerId: str,
        vaultVersion: str,
    ) -> None:
        now = datetime.utcnow()
        await self.states.update_one(
            {"chatId": chatId, "insightId": insightId},
            {
                "$set": {
                    "chatId": chatId,
                    "batchId": batchId,
                    "insightId": insightId,
                    "taken": True,
                    "answerId": answerId,
                    "answerIds": None,
                    "pendingReason": None,
                    "takenMeta": {
                        "source": "survey",
                        "mode": None,
                        "confidence": 1.0,
                        "evidence": [],
                        "vaultVersion": vaultVersion,
                    },
                    "updatedAt": now,
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )

    async def write_survey_multi(
        self,
        *,
        chatId: str,
        batchId: str,
        insightId: str,
        answerIds: List[str],
        vaultVersion: str,
    ) -> None:
        now = datetime.utcnow()
        await self.states.update_one(
            {"chatId": chatId, "insightId": insightId},
            {
                "$set": {
                    "chatId": chatId,
                    "batchId": batchId,
                    "insightId": insightId,
                    "taken": True,
                    "answerId": None,
                    "answerIds": list(answerIds),
                    "pendingReason": None,
                    "takenMeta": {
                        "source": "survey",
                        "mode": None,
                        "confidence": 1.0,
                        "evidence": [],
                        "vaultVersion": vaultVersion,
                    },
                    "updatedAt": now,
                },
                "$setOnInsert": {"createdAt": now},
            },
            upsert=True,
        )
# app/repositories/insight_vault_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import TypeAdapter

from app.core.settings import settings
from app.db.init_db import INSIGHT_VAULT
from app.models.insights import InsightBatch, Insight, InsightAnswer


class InsightVaultRepo:
    """
    Read-only access to the embedded Insight Vault (one doc per batch), and helpers
    for building the Stage-01 Vault Pack in the exact shape the LLM expects.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.col = db[INSIGHT_VAULT]
        self.version = settings.INSIGHT_VAULT_VERSION

    # ---------- Basic reads ----------

    async def list_active_batches(self) -> List[InsightBatch]:
        cur = self.col.find({"vaultVersion": self.version, "isActive": True})
        docs = await cur.to_list(None)
        # Validate/normalize via Pydantic
        adapter = TypeAdapter(List[InsightBatch])
        return adapter.validate_python(docs)

    async def get_batch(self, batchId: str) -> Optional[InsightBatch]:
        doc = await self.col.find_one(
            {"vaultVersion": self.version, "isActive": True, "batchId": batchId}
        )
        return InsightBatch.model_validate(doc) if doc else None

    async def list_active_insights_by_batch(self, batchId: str) -> List[Insight]:
        batch = await self.get_batch(batchId)
        if not batch:
            return []
        return [ins for ins in batch.insights if ins.isActive]

    async def list_active_insight_ids_by_batch(self, batchId: str) -> List[str]:
        insights = await self.list_active_insights_by_batch(batchId)
        return [i.insightId for i in insights]

    async def get_insight(self, insightId: str) -> Optional[Tuple[str, Insight]]:
        """
        Return (batchId, Insight) for an active insightId, or None.
        """
        # Find any active batch in this version containing the insightId
        cur = self.col.find(
            {"vaultVersion": self.version, "isActive": True, "insights.insightId": insightId},
            projection={"batchId": 1, "insights": 1},
        )
        async for doc in cur:
            for ins in doc.get("insights", []):
                if ins.get("insightId") == insightId and ins.get("isActive", True):
                    return doc["batchId"], Insight.model_validate(ins)
        return None

    async def validate_insight_and_answer(
        self,
        insightId: str,
        answerId: Optional[str] = None,
    ) -> Optional[Tuple[str, bool]]:
        """
        Validate that `insightId` exists and (if provided) `answerId` is valid under it.
        Returns (batchId, isMultiSelect) if valid; otherwise None.
        """
        found = await self.get_insight(insightId)
        if not found:
            return None
        batchId, insight = found
        if answerId is not None:
            if answerId not in insight.answers:
                return None
        return batchId, bool(insight.isMultiSelect)

    # ---------- Vault Pack for Stage-01 ----------

    async def build_vault_pack(self) -> Dict:
        """
        Produce the Vault Pack in the exact JSON shape the Stage-01 master prompt expects:
        {
          "batches":[{"batchId","name","language?"}, ...],
          "insights":[
            {
              "insightId","batchId","question",
              "answers": {"A":{"text","aliases":[]},"B":{...}},
              "isMultiSelect": false, "isActive": true
            }, ...
          ]
        }
        Only active batches/insights for the configured vaultVersion are included.
        """
        batches = await self.list_active_batches()

        batches_arr = [
            {"batchId": b.batchId, "name": b.name, **({"language": b.language} if b.language else {})}
            for b in batches
        ]

        insights_arr: List[Dict] = []
        for b in batches:
            for ins in b.insights:
                if not ins.isActive:
                    continue
                insights_arr.append(
                    {
                        "insightId": ins.insightId,
                        "batchId": b.batchId,
                        "question": ins.question,
                        "answers": {
                            ans_id: {"text": ans.text, "aliases": list(ans.aliases)}
                            for ans_id, ans in ins.answers.items()
                        },
                        "isMultiSelect": bool(ins.isMultiSelect),
                        "isActive": True,
                    }
                )

        return {"batches": batches_arr, "insights": insights_arr}

    # ---------- Convenience maps ----------

    async def build_insight_index(self) -> Dict[str, Dict]:
        """
        Map insightId -> { batchId, isMultiSelect, answers: {answerId: {text, aliases}} }
        for quick validation/lookup in services.
        """
        index: Dict[str, Dict] = {}
        batches = await self.list_active_batches()
        for b in batches:
            for ins in b.insights:
                if not ins.isActive:
                    continue
                index[ins.insightId] = {
                    "batchId": b.batchId,
                    "isMultiSelect": bool(ins.isMultiSelect),
                    "answers": {k: {"text": v.text, "aliases": list(v.aliases)} for k, v in ins.answers.items()},
                }
        return index


    # ---------- Component 10 needed ----------
    async def list_batches_in_order(self, *, include_answers: bool = False) -> List[Dict]:
        """
        Returns:
            [
            {
                "batchId": "<id>",
                "insights": [
                {"insightId": "<id>", "question": "<text>"}                        # default
                # if include_answers=True:
                # {"insightId": "<id>", "question": "<text>",
                #  "isMultiSelect": bool,
                #  "answers": {"A": {"text": "...", "aliases": [...]}, ...}}
                ]
            },
            ...
            ]
            Only active batches/insights for the current vaultVersion are included.
            Order matches the vault’s stored order.
        """
        batches = await self.list_active_batches()
        out: List[Dict] = []

        for b in batches:
            ins_arr: List[Dict] = []
            for ins in b.insights:
                if not ins.isActive:
                    continue
                item = {
                    "insightId": ins.insightId,
                    "question": ins.question,
                }
                if include_answers:
                    item["isMultiSelect"] = bool(ins.isMultiSelect)
                    item["answers"] = {
                        aid: {"text": a.text, "aliases": list(a.aliases)}
                        for aid, a in ins.answers.items()
                    }
                ins_arr.append(item)
            if ins_arr:
                out.append({"batchId": b.batchId, "insights": ins_arr})

        return out
# app/services/insight_completion.py
from __future__ import annotations

from typing import Dict, List, Set

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.insight_vault_repo import InsightVaultRepo
from app.repositories.chat_insights_repo import ChatInsightsRepo


async def list_fully_taken_batches(
    db: AsyncIOMotorDatabase,
    *,
    chatId: str,
) -> List[str]:
    """
    Return a list of batchIds where ALL active insights in that batch
    are taken (taken == true) for this chat.

    Notes:
    - Only considers *active* insights in the current vaultVersion.
    - Batches with 0 active insights are skipped.
    - Works regardless of whether 'taken' came from survey or auto-inference.
    """
    vault_repo = InsightVaultRepo(db)
    pcch_repo = ChatInsightsRepo(db)

    # 1) Read active batches + their active insightIds
    batches = await vault_repo.list_active_batches()
    batch_to_active_insights: Dict[str, Set[str]] = {
        b.batchId: {i.insightId for i in b.insights if i.isActive}
        for b in batches
    }

    # 2) Fetch taken/pending sets for this chat; we only need 'taken'
    taken_ids, _pending_ids = await pcch_repo.get_taken_and_pending(chatId)

    # 3) A batch is "fully taken" iff all its active insightIds ⊆ taken_ids
    fully_taken: List[str] = []
    for batch_id, active_insight_ids in batch_to_active_insights.items():
        if not active_insight_ids:
            # Skip empty batches (no active insights)
            continue
        if active_insight_ids.issubset(taken_ids):
            fully_taken.append(batch_id)

    return fully_taken


async def batch_completion_status(
    db: AsyncIOMotorDatabase,
    *,
    chatId: str,
) -> Dict[str, Dict[str, int | bool]]:
    """
    Optional helper: return per-batch completion stats.
    {
      "<batchId>": { "total": N, "taken": K, "isComplete": bool }
    }
    """
    vault_repo = InsightVaultRepo(db)
    pcch_repo = ChatInsightsRepo(db)

    batches = await vault_repo.list_active_batches()
    taken_ids, _pending_ids = await pcch_repo.get_taken_and_pending(chatId)

    out: Dict[str, Dict[str, int | bool]] = {}
    for b in batches:
        active_ids = [i.insightId for i in b.insights if i.isActive]
        total = len(active_ids)
        if total == 0:
            # Skip empty batches for clarity; uncomment to include with zeros
            # out[b.batchId] = {"total": 0, "taken": 0, "isComplete": True}
            continue
        k = sum(1 for iid in active_ids if iid in taken_ids)
        out[b.batchId] = {"total": total, "taken": k, "isComplete": (k == total)}
    return out

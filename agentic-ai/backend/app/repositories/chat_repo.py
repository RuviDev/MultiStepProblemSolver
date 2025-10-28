from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from app.db.init_db import CHAT_UIA_STATE
from app.models.chat import ChatUIAState, ChatInsightsUI, PendingPreview
from app.repositories.chat_insights_repo import ChatInsightsRepo

async def upsert_employment_category(db: AsyncIOMotorDatabase, chat_id: str, ec_id: str, vault_version: str):
    now = datetime.utcnow()
    # When EC changes, clear skills
    await db[CHAT_UIA_STATE].update_one(
        {"chat_id": chat_id},
        {"$set": {
            "employment_category_id": ec_id,
            "vault_version": vault_version,
            "updated_at": now
        },
         "$setOnInsert": {
            "recorded_at": now,
            "let_system_decide": False
        },
         "$unset": {"skills_selected": ""}},
        upsert=True
    )

async def get_chat_state(db: AsyncIOMotorDatabase, chat_id: str) -> dict | None:
    return await db[CHAT_UIA_STATE].find_one({"chat_id": chat_id}, {"_id": 0})

# async def get_chat_state(db, chat_id: str, user_id: str) -> ChatUIAState:
#     # --- Component 06 (existing state) ---
##     base_doc = await db[CHAT_UIA_STATE].find_one({"chatId": chat_id, "userId": user_id}) or {"chatId": chat_id}
#     base_doc = await db[CHAT_UIA_STATE].find_one({"chat_id": chat_id}, {"_id": 0})
#     state = ChatUIAState.model_validate(base_doc)  # <- this is the "state = ..." line

#     # --- Component 07 (overlay) ---
#     ci_repo = ChatInsightsRepo(db)
#     session = await ci_repo.get_session(chat_id) or {}
#     touched = session.get("touchedBatchIds", []) or []
#     pending_map = await ci_repo.list_pending_by_batch(chat_id, touched if touched else None)
#     stats_dict = session.get("insightStats", {"takenCount": 0, "pendingCount": 0})

#     state.insights = ChatInsightsUI(
#         insightStats=state.insights.insightStats.__class__(**stats_dict),
#         touchedBatchIds=touched,
#         pendingByBatch={
#             b: [PendingPreview(
#                     insightId=i["insightId"],
#                     pendingReason=i.get("pendingReason"),
#                     confidence=float(i.get("confidence", 0.0)),
#                 )
#                 for i in items
#             ]
#             for b, items in (pending_map or {}).items()
#         },
#     )

#     return state

async def upsert_skills_selection(
    db: AsyncIOMotorDatabase,
    chat_id: str,
    employment_category_id: str,
    skills_selected: Optional[List[str]],
    let_system_decide: bool,
    vault_version: str
):
    now = datetime.utcnow()
    if let_system_decide:
        await db[CHAT_UIA_STATE].update_one(
            {"chat_id": chat_id},
            {"$set": {
                "employment_category_id": employment_category_id,
                "let_system_decide": True,
                "vault_version": vault_version,
                "updated_at": now
            },
             "$unset": {"skills_selected": ""}},
            upsert=True
        )
    else:
        await db[CHAT_UIA_STATE].update_one(
            {"chat_id": chat_id},
            {"$set": {
                "employment_category_id": employment_category_id,
                "skills_selected": skills_selected or [],
                "let_system_decide": False,
                "vault_version": vault_version,
                "updated_at": now
            }},
            upsert=True
        )
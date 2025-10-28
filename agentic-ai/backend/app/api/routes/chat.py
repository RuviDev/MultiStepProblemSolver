from fastapi import APIRouter, HTTPException
from app.db.mongo import get_db
from app.repositories.chat_repo import get_chat_state

router = APIRouter(prefix="/chats", tags=["chats"])

@router.get("/{chat_id}/uia-state")
async def get_uia_state(chat_id: str):
    db = get_db()
    doc = await get_chat_state(db, chat_id)
    if not doc:
        # Return empty state instead of 404 to simplify UI
        return {
            "chat_id": chat_id,
            "employment_category_id": None,
            "skills_selected": None,
            "let_system_decide": False,
            "vault_version": None
        }
    return doc

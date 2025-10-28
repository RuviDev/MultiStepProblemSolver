from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db.mongo import get_db
from app.api.deps import get_current_user
from app.repositories.chats_repo import list_chats, create_chat, rename_chat, delete_chat

router = APIRouter(prefix="/chats", tags=["chats"])

@router.get("")
async def get_chats(user=Depends(get_current_user)):
    db = get_db()
    return await list_chats(db, user["id"])

class CreateChatReq(BaseModel):
    title: str | None = None

@router.post("")
async def create(user=Depends(get_current_user), payload: CreateChatReq = CreateChatReq()):
    db = get_db()
    cid = await create_chat(db, user["id"], payload.title)
    return {"id": cid, "title": payload.title or "Untitled chat"}

class RenameChatReq(BaseModel):
    title: str

@router.patch("/{chat_id}")
async def rename(chat_id: str, payload: RenameChatReq, user=Depends(get_current_user)):
    db = get_db()
    ok = await rename_chat(db, user["id"], chat_id, payload.title)
    if not ok:
        raise HTTPException(404, "Chat not found")
    return {"id": chat_id, "title": payload.title}

@router.delete("/{chat_id}")
async def delete(chat_id: str, user=Depends(get_current_user)):
    db = get_db()
    ok = await delete_chat(db, user["id"], chat_id)
    if not ok:
        raise HTTPException(404, "Chat not found")
    return {"ok": True}

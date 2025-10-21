import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from ..deps import get_current_user, get_db_dep
from ..models.chat import ChatCreate, ChatOut, ChatPatch

router = APIRouter()

@router.get("", response_model=list[ChatOut])
async def list_chats(request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    cur = db.chats.find({"user_id": ObjectId(user["id"])}).sort("created_at", -1)
    items = []
    async for c in cur:
        items.append(ChatOut(
            id=str(c["_id"]),
            title=c.get("title","New chat"),
            archived=bool(c.get("archived", False)),
            created_at=c["created_at"].isoformat(),
            updated_at=c["updated_at"].isoformat(),
        ))
    return items

@router.post("", response_model=ChatOut)
async def create_chat(request: Request, body: ChatCreate, user=Depends(get_current_user)):
    db = get_db_dep(request)
    now = datetime.datetime.utcnow()
    doc = {
        "user_id": ObjectId(user["id"]),
        "title": body.title or "New chat",
        "archived": False,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.chats.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ChatOut(id=str(doc["_id"]), title=doc["title"], archived=False, created_at=now.isoformat(), updated_at=now.isoformat())

@router.patch("/{chat_id}", response_model=ChatOut)
async def update_chat(chat_id: str, request: Request, body: ChatPatch, user=Depends(get_current_user)):
    db = get_db_dep(request)
    c = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if not c:
        raise HTTPException(status_code=404, detail="Chat not found")
    updates = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.archived is not None:
        updates["archived"] = bool(body.archived)
    updates["updated_at"] = datetime.datetime.utcnow()
    await db.chats.update_one({"_id": c["_id"]}, {"$set": updates})
    c.update(updates)
    return ChatOut(id=str(c["_id"]), title=c.get("title","New chat"), archived=bool(c.get("archived", False)),
                   created_at=c["created_at"].isoformat(), updated_at=c["updated_at"].isoformat())

@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    res = await db.chats.delete_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Chat not found")
    await db.messages.delete_many({"chat_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    return {"ok": True}

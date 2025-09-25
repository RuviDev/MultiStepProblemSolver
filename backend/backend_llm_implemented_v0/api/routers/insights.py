# api/routers/insights.py
from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from ..deps import get_current_user, get_db_dep

router = APIRouter()

@router.get("/{chat_id}")
async def get_insights(chat_id: str, request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    doc = await db.insights.find_one({"chat_id": chat["_id"], "user_id": ObjectId(user["id"])})
    if not doc:
        return {"insights": {}, "created_at": None, "updated_at": None}
    # make it API-friendly
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    doc["chat_id"] = str(doc["chat_id"])
    doc["user_id"] = str(doc["user_id"])
    return doc

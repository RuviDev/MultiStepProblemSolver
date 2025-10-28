from datetime import datetime
from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.db.init_db import CHATS

async def list_chats(db: AsyncIOMotorDatabase, user_id: str) -> List[dict]:
    cur = db[CHATS].find({"user_id": ObjectId(user_id)}).sort("last_message_at", -1)
    return [ { "id": str(d["_id"]), "title": d.get("title", "Untitled chat"),
               "last_message_at": d.get("last_message_at") } async for d in cur ]

async def create_chat(db: AsyncIOMotorDatabase, user_id: str, title: str | None) -> str:
    now = datetime.utcnow()
    doc = {"user_id": ObjectId(user_id), "title": title or "Untitled chat",
           "created_at": now, "updated_at": now, "last_message_at": now, "archived": False}
    res = await db[CHATS].insert_one(doc)
    return str(res.inserted_id)

async def rename_chat(db: AsyncIOMotorDatabase, user_id: str, chat_id: str, title: str) -> bool:
    res = await db[CHATS].update_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user_id)},
                                     {"$set": {"title": title, "updated_at": datetime.utcnow()}})
    return res.matched_count == 1

async def delete_chat(db: AsyncIOMotorDatabase, user_id: str, chat_id: str) -> bool:
    res = await db[CHATS].delete_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user_id)})
    return res.deleted_count == 1

async def verify_chat_owner(db: AsyncIOMotorDatabase, user_id: str, chat_id: str) -> bool:
    doc = await db[CHATS].find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user_id)})
    return doc is not None

async def touch_chat_activity(db: AsyncIOMotorDatabase, chat_id: str):
    await db[CHATS].update_one({"_id": ObjectId(chat_id)}, {"$set": {"last_message_at": datetime.utcnow()}})

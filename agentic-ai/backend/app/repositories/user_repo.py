from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.db.init_db import USERS

async def find_user_by_email(db: AsyncIOMotorDatabase, email: str) -> dict | None:
    return await db[USERS].find_one({"email": email.lower()})

async def find_user_by_id(db: AsyncIOMotorDatabase, user_id: str) -> dict | None:
    return await db[USERS].find_one({"_id": ObjectId(user_id)})

async def insert_user(db: AsyncIOMotorDatabase, email: str, password_hash: str) -> str:
    now = datetime.utcnow()
    doc = {"email": email.lower(), "password_hash": password_hash,
           "created_at": now, "updated_at": now, "status": "active", "last_login_at": None}
    res = await db[USERS].insert_one(doc)
    return str(res.inserted_id)

async def touch_login(db: AsyncIOMotorDatabase, user_id: str):
    await db[USERS].update_one({"_id": ObjectId(user_id)}, {"$set": {"last_login_at": datetime.utcnow()}})

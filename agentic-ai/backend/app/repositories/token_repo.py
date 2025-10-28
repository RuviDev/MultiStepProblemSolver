import hashlib
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.db.init_db import REFRESH_TOKENS

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

async def insert_refresh_token(db: AsyncIOMotorDatabase, user_id: str, token: str, expires_at: datetime, ua: str | None, ip: str | None):
    doc = {"user_id": ObjectId(user_id), "token_hash": _hash(token),
           "created_at": datetime.utcnow(), "expires_at": expires_at, "revoked": False,
           "user_agent": ua, "ip": ip}
    await db[REFRESH_TOKENS].insert_one(doc)

async def revoke_token(db: AsyncIOMotorDatabase, token: str):
    await db[REFRESH_TOKENS].update_one({"token_hash": _hash(token)}, {"$set": {"revoked": True}})

async def is_valid_refresh(db: AsyncIOMotorDatabase, token: str) -> dict | None:
    return await db[REFRESH_TOKENS].find_one({"token_hash": _hash(token), "revoked": False})

from datetime import datetime
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.init_db import UIA_EVENTS

async def insert_event(
    db: AsyncIOMotorDatabase,
    event_type: str,
    chat_id: str,
    payload: Optional[Dict[str, Any]] = None,
    vault_version: Optional[str] = None
):
    doc = {
        "ts": datetime.utcnow(),
        "type": event_type,
        "meta": {"chat_id": chat_id, "vault_version": vault_version},
        "payload": payload or {}
    }
    await db[UIA_EVENTS].insert_one(doc)

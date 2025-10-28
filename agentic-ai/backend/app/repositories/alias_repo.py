from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.init_db import VAULT_ALIAS_INDEX
from typing import Iterable

async def insert_many_aliases(db: AsyncIOMotorDatabase, items: Iterable[dict]) -> None:
    items = list(items)
    if not items:
        return
    await db[VAULT_ALIAS_INDEX].insert_many(items)

async def find_ec_by_alias(db: AsyncIOMotorDatabase, version: str, alias_norm: str) -> str | None:
    print("Finding EC by alias:", version, alias_norm)
    doc = await db[VAULT_ALIAS_INDEX].find_one({
        "vault_version": version,
        "alias_norm": alias_norm,
        "type": "ec"
    }, {"_id": 0, "target_id": 1})
    return doc["target_id"] if doc else None

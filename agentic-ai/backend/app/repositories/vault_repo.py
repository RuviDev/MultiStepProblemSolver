from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.init_db import SEGMENT_VAULT, CONFIG
from app.models.vault import SegmentVaultVersion
from typing import List, Dict, Any, Optional

async def get_active_vault_version(db: AsyncIOMotorDatabase) -> str | None:
    cfg = await db[CONFIG].find_one({"_id": "segment_vault"})
    return cfg.get("latest_version") if cfg else None

async def get_vault_by_version(db: AsyncIOMotorDatabase, version: str) -> dict | None:
    return await db[SEGMENT_VAULT].find_one({"vault_version": version}, {"_id": 0})

async def set_active_vault(db: AsyncIOMotorDatabase, version: str) -> None:
    await db[CONFIG].update_one({"_id": "segment_vault"},
                                {"$set": {"latest_version": version}},
                                upsert=True)

async def insert_vault(db: AsyncIOMotorDatabase, vault: SegmentVaultVersion) -> None:
    await db[SEGMENT_VAULT].insert_one(vault.model_dump())

async def list_ec_options(db: AsyncIOMotorDatabase, version: str) -> List[Dict[str, Any]]:
    doc = await db[SEGMENT_VAULT].find_one({"vault_version": version}, {"_id": 0, "employment_categories": 1})
    if not doc:
        return []
    return [
        {
            "id": ec["id"],
            "label": ec["name"],
            "desc": ec.get("description", "")
        }
        for ec in doc.get("employment_categories", [])
    ]

async def get_ec_by_id(db: AsyncIOMotorDatabase, version: str, ec_id: str) -> Optional[Dict[str, Any]]:
    doc = await db[SEGMENT_VAULT].find_one(
        {"vault_version": version, "employment_categories.id": ec_id},
        {"_id": 0, "employment_categories.$": 1}
    )
    if not doc:
        return None
    ecs = doc.get("employment_categories", [])
    return ecs[0] if ecs else None

async def list_skill_options_for_ec(db: AsyncIOMotorDatabase, version: str, ec_id: str) -> List[Dict[str, Any]]:
    ec = await get_ec_by_id(db, version, ec_id)
    if not ec:
        return []
    return [
        {
            "id": sk["id"],
            "label": sk["name"],
            "desc": sk.get("description", "")
        }
        for sk in ec.get("skills", [])
    ]

async def validate_skills_belong_to_ec(db: AsyncIOMotorDatabase, version: str, ec_id: str, skills: List[str]) -> bool:
    ec = await get_ec_by_id(db, version, ec_id)
    if not ec:
        return False
    valid = {sk["id"] for sk in ec.get("skills", [])}
    return set(skills).issubset(valid)
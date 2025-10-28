from fastapi import APIRouter, HTTPException
from app.db.mongo import get_db
from app.repositories.vault_repo import get_active_vault_version, get_vault_by_version

router = APIRouter(prefix="/segment-vault", tags=["segment-vault"])

@router.get("")
async def get_segment_vault(version: str = "latest"):
    db = get_db()
    if version == "latest":
        version = await get_active_vault_version(db)
        if not version:
            raise HTTPException(404, "No active vault")
    doc = await get_vault_by_version(db, version)
    if not doc:
        raise HTTPException(404, "Vault version not found")
    return doc

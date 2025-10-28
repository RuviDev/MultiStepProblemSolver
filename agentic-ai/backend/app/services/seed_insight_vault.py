# app/services/seed_insight_vault.py
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.settings import settings
from app.db.init_db import INSIGHT_VAULT

async def verify_or_seed(db: AsyncIOMotorDatabase) -> None:
    """Ensure the Insight Vault is present for the configured version.

    We *do not* silently seed here. If the version isn't present,
    raise an error instructing dev/ops to run the CLI seeder.
    """
    req_ver = settings.INSIGHT_VAULT_VERSION
    # any active doc in this version?
    count = await db[INSIGHT_VAULT].count_documents({"vaultVersion": req_ver, "isActive": True})
    if count == 0:
        # allow the collection to exist but the version missing
        existing = await db[INSIGHT_VAULT].estimated_document_count()
        if existing == 0:
            where = "collection is empty"
        else:
            where = "version not found"
        raise RuntimeError(
            f"[Insights] Vault not ready ({where}). "
            f"Expected vaultVersion='{req_ver}'. Run: python -m scripts.seed_insight_vault"
        )

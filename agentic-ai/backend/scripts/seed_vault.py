import asyncio
from app.db.mongo import get_db
from app.db.init_db import ensure_collections
from app.repositories.vault_repo import insert_vault, set_active_vault
from app.repositories.alias_repo import insert_many_aliases
from app.services.seed_vault import example_vault, build_alias_index

VAULT_VERSION = "2025-10-11#1"

async def main():
    db = get_db()
    await ensure_collections(db)

    vault = example_vault(VAULT_VERSION)
    # Insert vault snapshot
    await insert_vault(db, vault)
    # Build alias index
    alias_items = list(build_alias_index(vault))
    await insert_many_aliases(db, alias_items)
    # Point config to active version
    await set_active_vault(db, vault.vault_version)
    print(f"Seeded vault version {vault.vault_version} with {len(alias_items)} aliases.")

if __name__ == "__main__":
    asyncio.run(main())

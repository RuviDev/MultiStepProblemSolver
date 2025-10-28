# Defines collection names and an ensure_collections() function that creates all required indexes once:

from motor.motor_asyncio import AsyncIOMotorDatabase

# --- Component 06 (Insights) ---
SEGMENT_VAULT = "segment_vault_versions"
VAULT_ALIAS_INDEX = "vault_alias_index"
CHAT_UIA_STATE = "chat_uia_state"
CONFIG = "config"
UIA_EVENTS = "uia_events"
USERS = "users"
REFRESH_TOKENS = "refresh_tokens"
CHATS = "chats"
MESSAGES = "messages"

# --- Component 07 (Insights) ---
INSIGHT_VAULT = "insight_vault"
CHAT_INSIGHT_SESSIONS = "chat_insight_sessions" # one row per chat
CHAT_INSIGHT_STATES = "chat_insight_states"     # one row per {chatId, insightId}

async def ensure_collections(db: AsyncIOMotorDatabase) -> None:
    # Segment vault versions
    await db[SEGMENT_VAULT].create_index("vault_version", unique=True)
    await db[SEGMENT_VAULT].create_index("is_active")

    # Alias index
    # Unique EC aliases per version (e.g., "data scientist" once per vault_version)
    await db[VAULT_ALIAS_INDEX].create_index(
        [("vault_version", 1), ("type", 1), ("alias_norm", 1)],
        name="uniq_ec_alias_per_version",
        unique=True,
        partialFilterExpression={"type": "ec"}
    )

    # Unique Skill aliases per EC per version (e.g., "sql" can exist under different ECs)
    await db[VAULT_ALIAS_INDEX].create_index(
        [("vault_version", 1), ("type", 1), ("employment_category_id", 1), ("alias_norm", 1)],
        name="uniq_skill_alias_per_ec_per_version",
        unique=True,
        partialFilterExpression={"type": "skill"}
    )

    # Helper lookups (non-unique)
    await db[VAULT_ALIAS_INDEX].create_index([("vault_version", 1), ("type", 1)])
    await db[VAULT_ALIAS_INDEX].create_index([("vault_version", 1), ("alias_norm", 1)])

    # Chat state
    await db[CHAT_UIA_STATE].create_index("chat_id", unique=True)
    await db[CHAT_UIA_STATE].create_index("employment_category_id")

    # Events (optional)
    await db[UIA_EVENTS].create_index([("meta.chat_id", 1), ("ts", -1)])

    # Users
    await db[USERS].create_index("email", unique=True)

    # Refresh tokens
    await db[REFRESH_TOKENS].create_index("token_hash", unique=True)
    await db[REFRESH_TOKENS].create_index("user_id")
    # TTL index for expiry
    await db[REFRESH_TOKENS].create_index("expires_at", expireAfterSeconds=0)

    # Chats
    await db[CHATS].create_index([("user_id", 1), ("created_at", -1)])
    await db[CHATS].create_index([("user_id", 1), ("last_message_at", -1)])

    # Messages
    await db[MESSAGES].create_index([("chat_id", 1), ("created_at", 1)])
    await db[MESSAGES].create_index([("user_id", 1), ("created_at", -1)])


    # --- Component 07 (Insights) ---
    # Insight Vault: one document per batch (embedded insights[])
    await db[INSIGHT_VAULT].create_index("batchId", unique=True)
    await db[INSIGHT_VAULT].create_index("vaultVersion")
    await db[INSIGHT_VAULT].create_index("isActive")

    # Per-chat sessions: track touched batches and stats
    await db[CHAT_INSIGHT_SESSIONS].create_index("chatId", unique=True)
    await db[CHAT_INSIGHT_SESSIONS].create_index("touchedBatchIds")

    # Per-chat states: one per {chatId, insightId}
    await db[CHAT_INSIGHT_STATES].create_index([("chatId", 1), ("insightId", 1)], unique=True)
    await db[CHAT_INSIGHT_STATES].create_index([("chatId", 1), ("batchId", 1), ("taken", 1)])
    await db[CHAT_INSIGHT_STATES].create_index([("chatId", 1), ("taken", 1)])
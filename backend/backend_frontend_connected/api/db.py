import os
from typing import Any, Optional
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_CLIENT_KEY = "mongo_client"
MONGO_DB_KEY = "mongo_db"

_client: Optional[AsyncIOMotorClient] = None
_db = None

async def init_mongo(app: FastAPI) -> None:
    global _client, _db
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    dbname = os.getenv("MONGO_DB", "agentic")

    _client = AsyncIOMotorClient(uri, uuidRepresentation="standard")
    _db = _client[dbname]

    setattr(app.state, MONGO_CLIENT_KEY, _client)
    setattr(app.state, MONGO_DB_KEY, _db)

    await _ensure_indexes(_db)

async def _ensure_indexes(db):
    await db.users.create_index("email", unique=True)
    await db.chats.create_index([("user_id", 1), ("created_at", -1)])
    await db.messages.create_index([("chat_id", 1), ("created_at", 1)])
    await db.tokens_blacklist.create_index("jti", unique=True)
    await db.tokens_blacklist.create_index("exp", expireAfterSeconds=0)
    await db.thread_states.create_index("chat_id", unique=True)

def _get_db_from_state(request) -> Any:
    return getattr(request.app.state, MONGO_DB_KEY, None)

def _lazy_init_on_demand(request) -> Any:
    global _client, _db
    if _db is not None:
        return _db
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    dbname = os.getenv("MONGO_DB", "agentic")
    _client = AsyncIOMotorClient(uri, uuidRepresentation="standard")
    _db = _client[dbname]
    setattr(request.app.state, MONGO_CLIENT_KEY, _client)
    setattr(request.app.state, MONGO_DB_KEY, _db)
    return _db

def get_db(request) -> Any:
    db = _get_db_from_state(request)
    if db is not None:
        return db
    return _lazy_init_on_demand(request)

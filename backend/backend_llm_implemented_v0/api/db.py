import os
from typing import Any, Optional
from fastapi import FastAPI, Request
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_CLIENT_KEY = "mongo_client"
MONGO_DB_KEY = "mongo_db"

_client: Optional[AsyncIOMotorClient] = None
_db = None

async def ensure_indexes(db):
    # One insights doc per (user, chat)
    await db.insights.create_index([("user_id", 1), ("chat_id", 1)], unique=True)

async def init_mongo(app: FastAPI) -> None:
    global _client, _db
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    dbname = os.getenv("MONGO_DB", "agentic")
    _client = AsyncIOMotorClient(uri, uuidRepresentation="standard")
    _db = _client[dbname]

    from .db import ensure_indexes  # or relative import adjust as needed
    await ensure_indexes(_db)
    
    setattr(app.state, MONGO_CLIENT_KEY, _client)
    setattr(app.state, MONGO_DB_KEY, _db)

def _get_db_from_state(request: Request) -> Any:
    return getattr(request.app.state, MONGO_DB_KEY, None)

def _lazy_init_on_demand(request: Request) -> Any:
    # Fallback if startup hook didn't run in some envs (e.g., tests)
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

def get_db(request: Request) -> Any:
    db = _get_db_from_state(request)
    if db is not None:
        return db
    return _lazy_init_on_demand(request)

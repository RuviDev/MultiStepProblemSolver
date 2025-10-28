from typing import Optional, Dict, Any
from app.db.mongo import get_db
from app.repositories.events_repo import insert_event

async def emit_event(event_type: str, chat_id: str, payload: Optional[Dict[str, Any]] = None, vault_version: Optional[str] = None):
    db = get_db()
    await insert_event(db, event_type, chat_id, payload, vault_version)

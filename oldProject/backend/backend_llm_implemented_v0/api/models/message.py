from pydantic import BaseModel
from typing import Optional, Any, Dict

class SendMessageIn(BaseModel):
    prompt: str

class MessageOut(BaseModel):
    id: str
    role: str
    content_md: str
    provider: Optional[str] = None
    created_at: str
    agent_meta: Optional[Dict[str, Any]] = None

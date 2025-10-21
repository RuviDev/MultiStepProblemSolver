from pydantic import BaseModel
from typing import Optional

class ChatCreate(BaseModel):
    title: Optional[str] = None

class ChatOut(BaseModel):
    id: str
    title: str
    archived: bool
    created_at: str
    updated_at: str

class ChatPatch(BaseModel):
    title: Optional[str] = None
    archived: Optional[bool] = None

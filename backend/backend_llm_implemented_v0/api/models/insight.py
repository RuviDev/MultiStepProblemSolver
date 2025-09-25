# api/models/insight.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Union
from datetime import datetime

InsightSource = Literal["auto_extract", "survey", "explicit_message", "imported", "default"]

class EnumField(BaseModel):
    value: Union[str, List[str]]
    confidence: float = Field(ge=0, le=1, default=0.9)
    source: InsightSource = "auto_extract"
    evidence: List[str] = []
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class InsightState(BaseModel):
    # meta is stored in Mongo but not needed from the client
    goal_type: Optional[EnumField] = None
    deadline_profile: Optional[EnumField] = None
    tradeoff_priority: Optional[EnumField] = None

    modality: Optional[EnumField] = None              # list[str]
    interactivity_level: Optional[EnumField] = None
    availability_windows: Optional[EnumField] = None  # list[str]
    session_length: Optional[EnumField] = None

    chunk_size: Optional[EnumField] = None
    ramp_rate: Optional[EnumField] = None
    parallelism: Optional[EnumField] = None
    checkpoint_frequency: Optional[EnumField] = None

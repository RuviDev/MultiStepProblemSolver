from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from typing import Dict, List, Optional
from app.models.insights import InsightStats

class PendingPreview(BaseModel):
    insightId: str
    pendingReason: Optional[str] = None
    confidence: float = 0.0

class ChatInsightsUI(BaseModel):
    insightStats: InsightStats = Field(default_factory=InsightStats)
    touchedBatchIds: List[str] = Field(default_factory=list)
    # { batchId: [ {insightId, pendingReason, confidence}, ... ] }
    pendingByBatch: Dict[str, List[PendingPreview]] = Field(default_factory=dict)

class ChatUIAState(BaseModel):
    chat_id: str
    employment_category_id: Optional[str] = None
    skills_selected: Optional[List[str]] = None
    let_system_decide: bool = False
    vault_version: str
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    insights: ChatInsightsUI = Field(default_factory=ChatInsightsUI)

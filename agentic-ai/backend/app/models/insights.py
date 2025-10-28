# app/models/insights.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict, model_validator


# =========================
# Insight Vault (embedded)
# =========================

class InsightAnswer(BaseModel):
    text: str
    aliases: List[str] = Field(default_factory=list)


class Insight(BaseModel):
    insightId: str
    question: str
    isMultiSelect: bool = False
    isActive: bool = True
    # Answers keyed by answerId ("A", "B", "C", ...)
    answers: Dict[str, InsightAnswer] = Field(default_factory=dict)


class InsightBatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    batchId: str
    name: str
    language: Optional[str] = None
    isActive: bool = True
    vaultVersion: str

    insights: List[Insight] = Field(default_factory=list)

    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)


# ==================================
# Per-Chat Conversation History (PCCH)
# ==================================

class InsightStats(BaseModel):
    takenCount: int = 0
    pendingCount: int = 0


class ChatInsightSession(BaseModel):
    chatId: str
    touchedBatchIds: List[str] = Field(default_factory=list)
    insightStats: InsightStats = Field(default_factory=InsightStats)
    vaultVersion: str

    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)


PendingReason = Optional[Literal["question_only", "batch_fill"]]
Source = Literal["auto-inference", "survey", "batch-expansion"]
Mode = Optional[Literal["qa", "answer_only"]]


class TakenMeta(BaseModel):
    source: Source
    mode: Mode = None
    confidence: float
    evidence: List[str] = Field(default_factory=list)
    vaultVersion: str


class ChatInsightState(BaseModel):
    """
    One row per {chatId, insightId}.
    Note: For pending rows (taken=None), both answerId and answerIds must be null.
    For taken rows (taken=True):
      - exactly one of answerId XOR answerIds must be set.
    """
    chatId: str
    batchId: str
    insightId: str

    taken: Optional[bool] = None
    # single-select result
    answerId: Optional[str] = None
    # multi-select result
    answerIds: Optional[List[str]] = None

    pendingReason: PendingReason = None
    takenMeta: TakenMeta
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def _validate_answers_vs_taken(self):
        if self.taken is None:
            # pending rows must not carry answers
            if self.answerId is not None or self.answerIds not in (None, []):
                raise ValueError("Pending rows (taken=null) must not include answerId(s).")
        else:
            # taken == True
            single = self.answerId is not None
            multi = self.answerIds is not None and len(self.answerIds) > 0
            if single == multi:
                raise ValueError("For taken rows, set exactly one of answerId XOR answerIds.")
        return self


# =========================
# Stage-02 Survey DTOs
# =========================

QuestionType = Literal["single", "multi"]

class SurveyQuestionOption(BaseModel):
    answerId: str
    label: str


class SurveyQuestion(BaseModel):
    insightId: str
    uiQuestion: str
    type: QuestionType
    options: List[SurveyQuestionOption]
    includeOther: bool = True
    noteOtherLabel: str = "Other (write-in)"


class SurveyPayload(BaseModel):
    batchId: str
    title: str
    language: str = "en"
    questions: List[SurveyQuestion]
    ordering: Literal["question_only_first"] = "question_only_first"

# new
class InsightSurveyEnvelope(BaseModel):
    surveyType: Literal["insight"] = "insight"
    vaultVersion: Optional[str] = None
    language: str = "en"
    batches: List[SurveyPayload]  # Each SurveyPayload is one batch


class SurveyResponse(BaseModel):
    insightId: str
    # Either answerId (single) or answerIds[] (multi)
    answerId: Optional[str] = None
    answerIds: Optional[List[str]] = None

    @model_validator(mode="after")
    def _validate_choice(self):
        single = self.answerId is not None
        multi = self.answerIds is not None and len(self.answerIds) > 0
        if single == multi:
            raise ValueError("Provide exactly one of answerId XOR answerIds.")
        return self


class SurveySubmission(BaseModel):
    chatId: str
    msgId: str
    batchId: str
    responses: List[SurveyResponse]
    submittedAt: datetime

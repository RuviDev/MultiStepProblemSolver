import os, traceback
from typing import Any, Optional
from .repo_mongo import MemoryRepoMongo
from .summarizer import summarize

class MemoryService:
    def __init__(self):
        self.enabled = os.getenv("MEMORY_DB_ENABLED", "false").lower() == "true"
        self.summarizer_enabled = os.getenv("MEMORY_SUMMARIZER_ENABLED", "false").lower() == "true"
        self.uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.dbname = os.getenv("MONGO_DB", "agentic")
        self.repo = MemoryRepoMongo(self.uri, self.dbname) if self.enabled else None

    def _safe(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            print("[MemoryService] non-fatal error:", traceback.format_exc())
            return None

    def log_asked(self, problem_id: str, field_id: str, options_payload: Any):
        if not self.enabled or not self.repo: return
        self._safe(self.repo.log_event, problem_id, field_id, "asked", options_payload)

    def log_answered(self, problem_id: str, field_id: str, raw_payload: Any):
        if not self.enabled or not self.repo: return
        self._safe(self.repo.log_event, problem_id, field_id, "answered", raw_payload)

    def save_insight(self, problem_id: str, field_id: str, value: Any,
                     source: str, confidence: float,
                     user_id: Optional[str] = None, chat_id: Optional[str] = None,
                     label: Optional[str] = None):
        if not self.enabled or not self.repo: return None
        insight_id = self._safe(self.repo.upsert_insight,
                                problem_id, field_id, value, source, confidence, user_id, chat_id)
        if self.summarizer_enabled and insight_id and label is not None:
            summary_md, rationale_md, provider, model_name = summarize(label, value, source, confidence)
            self._safe(self.repo.save_summary, insight_id, summary_md, rationale_md, provider, model_name)
        return insight_id

from typing import Any, Dict, Optional
from datetime import datetime
from pymongo import MongoClient, ASCENDING

class MemoryRepoMongo:
    def __init__(self, uri: str, dbname: str):
        self.client = MongoClient(uri, uuidRepresentation="standard")
        self.db = self.client[dbname]
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.db.insights.create_index([("problem_id", ASCENDING), ("field_id", ASCENDING)], unique=True)
        self.db.insight_summaries.create_index([("insight_id", ASCENDING)], unique=True)
        self.db.survey_events.create_index([("problem_id", ASCENDING), ("created_at", ASCENDING)])

    def upsert_insight(self,
                       problem_id: str,
                       field_id: str,
                       value_json: Any,
                       source: str,
                       confidence: float,
                       user_id: Optional[str] = None,
                       chat_id: Optional[str] = None) -> Any:
        now = datetime.utcnow()
        doc = {
            "problem_id": problem_id, "field_id": field_id,
            "value": value_json, "source": source, "confidence": float(confidence),
            "user_id": user_id, "chat_id": chat_id,
            "updated_at": now
        }
        self.db.insights.update_one(
            {"problem_id": problem_id, "field_id": field_id},
            {"$set": doc, "$setOnInsert": {"created_at": now, "version": 1}},
            upsert=True
        )
        found = self.db.insights.find_one({"problem_id": problem_id, "field_id": field_id}, {"_id": 1})
        return found["_id"] if found else None

    def save_summary(self, insight_id: Any, summary_md: str, rationale_md: Optional[str],
                     model_provider: Optional[str], model_name: Optional[str]) -> None:
        now = datetime.utcnow()
        self.db.insight_summaries.update_one(
            {"insight_id": insight_id},
            {"$set": {
                "insight_id": insight_id,
                "summary_md": summary_md,
                "rationale_md": rationale_md,
                "model_provider": model_provider,
                "model_name": model_name,
                "updated_at": now
            }, "$setOnInsert": {"created_at": now}},
            upsert=True
        )

    def log_event(self, problem_id: str, field_id: str, event: str, payload_json: Any) -> None:
        self.db.survey_events.insert_one({
            "problem_id": problem_id, "field_id": field_id,
            "event": event, "payload": payload_json, "created_at": datetime.utcnow()
        })

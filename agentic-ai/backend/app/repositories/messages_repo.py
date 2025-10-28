from datetime import datetime
from typing import List, Literal, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.db.init_db import MESSAGES

from pydantic import BaseModel

Role = Literal["user", "assistant"]

# async def list_messages(db: AsyncIOMotorDatabase, user_id: str, chat_id: str) -> List[dict]:
#     cur = db[MESSAGES].find({"chat_id": ObjectId(chat_id), "user_id": ObjectId(user_id)}).sort("created_at", 1)
#     out = []
#     async for d in cur:
#         m = {"id": str(d["_id"]), "role": d["role"], "type": d.get("type", "text"), "content": d.get("content", "")}
#         if d.get("survey"): m["survey"] = d["survey"]
#         out.append(m)
#     return out

def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    # ensure ISO 8601; add 'Z' if naive UTC
    s = dt.isoformat()
    return s if s.endswith("Z") else (s + "Z")

async def list_messages(db: AsyncIOMotorDatabase, user_id: str, chat_id: str) -> List[dict]:
    cur = db[MESSAGES].find({"chat_id": ObjectId(chat_id), "user_id": ObjectId(user_id)}).sort("created_at", 1)

    out: List[dict] = []
    async for d in cur:
        m = {
                "id": str(d["_id"]),
                "role": d["role"],
                "type": d.get("type", "text"),                 # keep 'text' for most; 'progress' for loaders; legacy safe
                "content": d.get("content", ""),
                # "enc_question": d.get("enc_question", ""),     # creative nudge (may be empty)
            }
        if d.get("survey"):
            m["surveyType"] = d["surveyType"]
            m["survey"] = d["survey"]
        if d.get("enc_question"):
            m["enc_question"] = d["enc_question"]
        if d.get("sources"):
            m["sources"] = d["sources"]

        out.append(m)
    return out

def _bsonify(obj):
    # Convert Pydantic models (and any nested structures) to plain JSON-like values
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, (list, tuple)):
        return [_bsonify(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _bsonify(v) for k, v in obj.items()}
    return obj  # primitives pass through

# async def insert_message(
#     db: AsyncIOMotorDatabase,
#     user_id: str,
#     chat_id: str,
#     role: str,
#     *,
#     content: str | None = None,
#     type: str = "text",
#     survey: object | None = None,
#     blocks: object | None = None,
# ):
#     doc = {
#         "user_id": ObjectId(user_id),
#         "chat_id": ObjectId(chat_id),
#         "role": role,
#         "type": type,
#         "content": content or "",
#         "created_at": datetime.utcnow(),
#     }

#     if survey is not None:
#         doc["survey"] = _bsonify(survey)   # <-- convert here

#     if blocks is not None:
#         doc["blocks"] = _bsonify(blocks)   # <-- and here (future composite messages)

#     await db[MESSAGES].insert_one(doc)

async def insert_message(
    db: AsyncIOMotorDatabase,
    user_id: str,
    chat_id: str,
    role: str,
    *,
    content: str | None = None,
    type: str = "text",
    survey_type: str | None = None,
    survey: object | None = None,
    enc_question: str | None = None,
    blocks: object | None = None,
    sources: object | None = None,
    scope_label: str | None = None,
):
    doc = {
        "user_id": ObjectId(user_id),
        "chat_id": ObjectId(chat_id),
        "role": role,
        "type": type,
        "content": content or "",
        "created_at": datetime.utcnow(),
    }

    if survey_type is not None:
        doc["surveyType"] = survey_type     # camelCase to match frontend

    if survey is not None:
        doc["survey"] = _bsonify(survey)

    if enc_question is not None:
        doc["enc_question"] = enc_question

    if blocks is not None:
        doc["blocks"] = _bsonify(blocks)

    if sources is not None:          # <-- NEW
        doc["sources"] = _bsonify(sources)

    if scope_label is not None:
        doc["scope_label"] = scope_label

    res = await db[MESSAGES].insert_one(doc)
    # print("Inserted message ID:", res)
    return str(res.inserted_id)

async def update_insight_survey_message_with_submission_by_id(
    db: AsyncIOMotorDatabase,
    *,
    user_id: str,
    chat_id: str,
    msg_id: str,
    batch_id: str,
    submission: Dict[str, Any],   # e.g. {"responses":[...], "submittedAt": "..."}
) -> bool:
    """
    Finds the most recent assistant message of type 'insight-survey' in this chat,
    and records the submission under survey.submittedBatches[batch_id].
    Also sets survey.isSubmitted=True if all batches in survey.batches are submitted.
    """
    filt = {
        "_id": ObjectId(msg_id),
        "user_id": ObjectId(user_id),
        "chat_id": ObjectId(chat_id),
        "role": "assistant",
    }
    doc = await db[MESSAGES].find_one(filt, projection={"survey": 1})
    if not doc:
        return False

    survey = (doc.get("survey") or {})
    batches = [b.get("batchId") for b in (survey.get("batches") or [])]

    # Build the new submittedBatches map in memory to evaluate completeness
    existing = dict(survey.get("submittedBatches") or {})
    existing[batch_id] = submission

    all_submitted = bool(batches) and all(bid in existing for bid in batches)

    update = {
        "$set": {
            f"survey.submittedBatches.{batch_id}": submission,
            "updated_at": datetime.utcnow(),
        }
    }
    if all_submitted:
        update["$set"]["survey.isSubmitted"] = True

    res = await db[MESSAGES].update_one(filt, update)
    # Treat a matched-but-not-modified case (same payload) as success
    return res.matched_count == 1
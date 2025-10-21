
import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId

from ..deps import get_current_user, get_db_dep
from ..models.message import SendMessageIn, MessageOut
from ..insights.extract import extract_insights
from ..services.rag_service import query_rag_for_prompt

router = APIRouter()

@router.get("/{chat_id}", response_model=list[MessageOut])
async def list_messages(chat_id: str, request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    items: List[MessageOut] = []
    cur = db.messages.find({"chat_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])}).sort("created_at", 1)
    async for m in cur:
        items.append(MessageOut(
            id=str(m["_id"]),
            role=m["role"],
            content_md=m["content_md"],
            provider=m.get("provider"),
            created_at=m["created_at"].isoformat(),
            agent_meta=m.get("agent_meta"),
        ))
    return items

def _merge_enum_field(old: dict | None, new: dict) -> dict:
    """
    Merges EnumField-like dicts. Multi-value fields use union.
    """
    if not old:
        return new
    ov, nv = old.get("value"), new.get("value")
    if isinstance(ov, list) or isinstance(nv, list):
        # multi-value union, normalize to sorted unique
        ovl = ov if isinstance(ov, list) else ([ov] if ov else [])
        nvl = nv if isinstance(nv, list) else ([nv] if nv else [])
        merged = sorted({*ovl, *nvl})
        conf = max(float(old.get("confidence", 0)), float(new.get("confidence", 0)))
        ev = (old.get("evidence", []) + new.get("evidence", []))[:5]
        return {"value": merged, "confidence": conf, "source": old.get("source", "auto_extract"), "evidence": ev, "updated_at": datetime.utcnow()}
    else:
        # single value: replace only if new is more confident
        if float(new.get("confidence", 0)) >= float(old.get("confidence", 0)):
            ev = (old.get("evidence", []) + new.get("evidence", []))[:5]
            out = new.copy()
            out["evidence"] = ev
            out["updated_at"] = datetime.utcnow()
            return out
        return old

async def _upsert_insights(db, user_id: ObjectId, chat_oid: ObjectId, candidates: dict):
    base_filter = {"user_id": user_id, "chat_id": chat_oid}
    doc = await db.insights.find_one(base_filter)
    if not doc:
        doc = {**base_filter, "created_at": datetime.utcnow(), "updated_at": datetime.utcnow()}
        try:
            await db.insights.insert_one(doc)
        except Exception:
            pass  # race-safe
    updates: Dict[str, Any] = {}
    for k, newv in (candidates or {}).items():
        oldv = doc.get(k)
        merged = _merge_enum_field(oldv, newv)
        if merged != oldv:
            updates[k] = merged
    if updates:
        updates["updated_at"] = datetime.utcnow()
        await db.insights.update_one(base_filter, {"$set": updates})

@router.post("/{chat_id}", response_model=MessageOut)
async def send_message(chat_id: str, body: SendMessageIn, request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # 1) Save user message
    user_msg = {
        "chat_id": chat["_id"],
        "user_id": ObjectId(user["id"]),
        "role": "user",
        "content_md": body.prompt,
        "created_at": datetime.utcnow(),
    }
    res1 = await db.messages.insert_one(user_msg)
    user_msg_id = res1.inserted_id

    print ("Body prompt:", body.prompt)

    # 2) Extract & upsert insights for THIS chat
    candidates = extract_insights(body.prompt or "")
    print("Extracted candidates:", candidates)
    await _upsert_insights(db, ObjectId(user["id"]), chat["_id"], candidates)

    # 3) Read current insight state to inform RAG
    insight_doc = await db.insights.find_one({"chat_id": chat["_id"], "user_id": ObjectId(user["id"])}) or {}
    insight_state = {k: v for k, v in insight_doc.items() if k not in {"_id","user_id","chat_id","created_at","updated_at","ready_for_planning","problem_statement"}}
    print("Current insight state:", insight_state)

    # 4) Query RAG
    evidence_pack = await query_rag_for_prompt(body.prompt or "", insight_state)
    print("RAG evidence pack:", evidence_pack)

    # 5) (Optional) Persist evidence
    try:
        await db.evidence.insert_one({
            "chat_id": chat["_id"],
            "user_id": ObjectId(user["id"]),
            "message_id": user_msg_id,
            "pack": evidence_pack,
            "created_at": datetime.utcnow(),
        })
    except Exception:
        pass

    # 6) Build chat history (last 8 messages)
    history: List[Dict[str, str]] = []
    cursor = db.messages.find({"chat_id": chat["_id"]}).sort("created_at", -1).limit(8)
    async for row in cursor:
        history.append({"role": row.get("role","assistant"), "content": row.get("content_md","")})
    history = list(reversed(history))

    print("Chat history:", history)

    # 7) Call LLM orchestrator
    from ..services.llm_orchestrator import call_llm
    llm_json = call_llm(body.prompt or "", history, insight_state, evidence_pack)

    # 8) If model suggested an insight_update, apply to DB
    try:
        upd = llm_json.get("insight_update")
    except Exception:
        upd = None
    if upd and isinstance(upd, dict) and upd.get("field_id") and "value" in upd:
        field_id = upd["field_id"]
        value = upd["value"]
        newv = {"value": value, "confidence": float(upd.get("confidence", 0.9)), "source": "explicit_message", "evidence": ["llm"], "updated_at": datetime.utcnow()}
        doc = await db.insights.find_one({"chat_id": chat["_id"], "user_id": ObjectId(user["id"])}) or {}
        oldv = doc.get(field_id)
        merged = _merge_enum_field(oldv, newv)
        await db.insights.update_one({"chat_id": chat["_id"], "user_id": ObjectId(user["id"])}, {"$set": {field_id: merged, "updated_at": datetime.utcnow()}})

    # 9) If READY_FOR_PLANNING, persist problem_statement into insights doc
    if llm_json.get("type") == "READY_FOR_PLANNING" and isinstance(llm_json.get("problem_statement"), dict):
        await db.insights.update_one({"chat_id": chat["_id"], "user_id": ObjectId(user["id"])},
            {"$set": {"ready_for_planning": True, "problem_statement": llm_json["problem_statement"], "updated_at": datetime.utcnow()}})

    # 10) Compose assistant message
    msg_text = llm_json.get("message") or "Okay."
    # evidence only when model says so
    bullets_view = ""
    if llm_json.get("use_evidence") and evidence_pack.get("results"):
        bullets_view = "\n\n**Evidence:**\n" + "\n".join(
            f"- [{r['anchor_id']}] {r['bullets'][0] if r['bullets'] else ''} *(src: {r['source_doc']})*"
            for r in evidence_pack["results"][:1]
        )
    asst_content = msg_text + bullets_view

    asst = {
        "chat_id": chat["_id"],
        "user_id": ObjectId(user["id"]),
        "role": "assistant",
        "content_md": asst_content,
        "provider": os.getenv("LLM_PROVIDER","openai") if os.getenv("OPENAI_API_KEY") else "uaa-fallback",
        "agent_meta": {"mode": "uaa", "llm_json": llm_json},
        "created_at": datetime.utcnow(),
    }
    res2 = await db.messages.insert_one(asst)

    return MessageOut(
        id=str(res2.inserted_id),
        role="assistant",
        content_md=asst_content,
        provider=asst["provider"],
        created_at=asst["created_at"].isoformat(),
        agent_meta=asst["agent_meta"],
    )

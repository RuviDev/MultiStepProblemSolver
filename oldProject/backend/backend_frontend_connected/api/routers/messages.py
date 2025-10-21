import datetime, json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from ..deps import get_current_user, get_db_dep
from ..models.message import SendMessageIn, MessageOut
from ..services.agent_bridge import run_turn, compute_paths

router = APIRouter()

@router.get("/{chat_id}", response_model=list[MessageOut])
async def list_messages(chat_id: str, request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    cur = db.messages.find({"chat_id": chat["_id"]}).sort("created_at", 1)
    out = []
    async for m in cur:
        out.append(MessageOut(
            id=str(m["_id"]), role=m["role"], content_md=m.get("content_md",""),
            provider=m.get("provider"), created_at=m["created_at"].isoformat(),
            agent_meta=m.get("agent_meta")
        ))
    return out

@router.post("/{chat_id}", response_model=MessageOut)
async def send_message(chat_id: str, body: SendMessageIn, request: Request, user=Depends(get_current_user)):
    db = get_db_dep(request)
    chat = await db.chats.find_one({"_id": ObjectId(chat_id), "user_id": ObjectId(user["id"])})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Restore state if missing from DB snapshot (durable memory)
    _, state_path, out_dir, _, _ = compute_paths(chat_id)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts_doc = await db.thread_states.find_one({"chat_id": chat["_id"]})
    if not Path(state_path).exists() and ts_doc and "thread_state" in ts_doc:
        Path(state_path).write_text(json.dumps(ts_doc["thread_state"], ensure_ascii=False), encoding="utf-8")

    now = datetime.datetime.utcnow()
    user_msg = {"chat_id": chat["_id"], "user_id": ObjectId(user["id"]), "role": "user",
                "content_md": body.prompt, "created_at": now}
    await db.messages.insert_one(user_msg)

    final_md, final_json, req_env, paths = run_turn(chat_id, body.prompt)

    # Snapshot thread_state to DB for durability
    try:
        spath = Path(paths["state_path"])
        if spath.exists():
            ts_json = json.loads(spath.read_text(encoding="utf-8"))
            await db.thread_states.update_one(
                {"chat_id": chat["_id"]},
                {"$set": {
                    "chat_id": chat["_id"],
                    "thread_state": ts_json,
                    "history_summary": ts_json.get("history_summary"),
                    "active_problem_id": (ts_json.get("problem_records") or [{}])[-1].get("problem_id") if ts_json.get("problem_records") else None,
                    "updated_at": datetime.datetime.utcnow()
                }, "$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
                upsert=True
            )
    except Exception:
        pass

    meta = {
        "request_envelope": req_env,
        "final_response_json": final_json,
        "evidence_anchors": (req_env.get("step6",{}) or {}).get("results", [])
    }
    asst = {"chat_id": chat["_id"], "user_id": ObjectId(user["id"]), "role": "assistant",
            "content_md": final_md, "provider": final_json.get("provider"),
            "agent_meta": meta, "created_at": datetime.datetime.utcnow()}
    res2 = await db.messages.insert_one(asst)
    m_id = res2.inserted_id

    return MessageOut(id=str(m_id), role="assistant", content_md=final_md,
                      provider=final_json.get("provider"),
                      created_at=asst["created_at"].isoformat(), agent_meta=meta)

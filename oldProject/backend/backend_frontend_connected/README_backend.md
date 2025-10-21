# FastAPI Wrapper (Phases 0–5) — Non‑intrusive
This adds auth, chats, messages, and an agent bridge to your existing project **without changing agent logic**.

## Install
```bash
python -m venv .venv
# Windows
. .venv\Scripts\activate
pip install -r requirements-api.txt
```
Copy `.env.example` → `.env` and set Mongo URI, JWT secret, and agent paths.

## Run
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Flow
1) `POST /auth/signup` → get tokens
2) `POST /chats` (Bearer) → creates a chat
3) `POST /messages/{chat_id}` (Bearer, { "prompt": "..." }) → runs the agent and returns assistant message
4) `GET /messages/{chat_id}` (Bearer) → history

## In‑process option
Set `AGENT_RUN_MODE=inproc` and keep `agent8/turn_api.py` (provided).

## (Optional) Enable Insights → Mongo + Summaries
```
MEMORY_DB_ENABLED=true
MONGO_URI=mongodb://localhost:27017
MONGO_DB=agentic
MEMORY_SUMMARIZER_ENABLED=true
MEMORY_SUMMARIZER_USE_LLM=false
```

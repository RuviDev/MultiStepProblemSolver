# Minimal Backend (Auth + Chats + Messages)

This is a trimmed FastAPI backend extracted from your archive, keeping only:
- DB connection (MongoDB via Motor)
- Pydantic models (user handled inline via Mongo docs; chats, messages)
- Authentication endpoints: **/auth/signup, /auth/signin, /auth/refresh, /auth/logout**
- Chat endpoints: **/chats** (list/create/patch/delete)
- Message endpoints: **/messages/{chat_id}** (list, send)
- Health: **/health**

**RAG/agent files and other services are removed.** The `send` endpoint just echoes the prompt.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # then edit values
uvicorn api.main:app --reload --port 8000
```

## ENV
- `MONGO_URI` (default: mongodb://localhost:27017)
- `MONGO_DB` (default: agentic)
- `JWT_SECRET` (change this!)
- `JWT_ALG` (default: HS256)
- `JWT_ACCESS_TTL_MIN` (default: 15)
- `JWT_REFRESH_TTL_DAYS` (default: 7)
- `CORS_ORIGINS` (comma-separated; default: *)

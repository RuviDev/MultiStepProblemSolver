import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from .db import init_mongo
from .routers import auth, chats, messages, insights

load_dotenv()

app = FastAPI(title="Agentic Minimal API", version="0.1.0")

origins = [o.strip() for o in (os.getenv("CORS_ORIGINS","*").split(","))]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await init_mongo(app)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(chats.router, prefix="/chats", tags=["chats"])
app.include_router(messages.router, prefix="/messages", tags=["messages"])
app.include_router(insights.router, prefix="/insights", tags=["insights"])


@app.get("/health")
async def health():
    return {"ok": True}


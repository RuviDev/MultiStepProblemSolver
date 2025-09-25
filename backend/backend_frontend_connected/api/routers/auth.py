import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from ..db import get_db
from ..security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from ..models.auth import SignupIn, SigninIn, TokenPair

router = APIRouter()

@router.post("/signup", response_model=TokenPair)
async def signup(req: Request, body: SignupIn):
    db = get_db(req)
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    doc = {
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "created_at": datetime.datetime.utcnow(),
        "updated_at": datetime.datetime.utcnow()
    }
    res = await db.users.insert_one(doc)
    user_id = str(res.inserted_id)
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    return TokenPair(access_token=access, refresh_token=refresh)

@router.post("/signin", response_model=TokenPair)
async def signin(req: Request, body: SigninIn):
    db = get_db(req)
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user_id = str(user["_id"])
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    return TokenPair(access_token=access, refresh_token=refresh)

@router.post("/refresh", response_model=TokenPair)
async def refresh(req: Request, refresh_token: str):
    try:
        payload = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh payload")
    access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    return TokenPair(access_token=access, refresh_token=new_refresh)

@router.post("/logout")
async def logout():
    return {"ok": True}

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from app.db.mongo import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.repositories.user_repo import find_user_by_email, insert_user, touch_login
from app.repositories.token_repo import insert_refresh_token, is_valid_refresh, revoke_token
from jose import JWTError, jwt

router = APIRouter(prefix="/auth", tags=["auth"])

class SignReq(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str

@router.post("/signup", response_model=TokenPair)
async def signup(req: SignReq, request: Request):
    db = get_db()
    if await find_user_by_email(db, req.email):
        raise HTTPException(400, "Email already exists")
    uid = await insert_user(db, req.email, hash_password(req.password))
    at = create_access_token(uid)
    rt, exp = create_refresh_token(uid)
    await insert_refresh_token(db, uid, rt, exp, request.headers.get("user-agent"), request.client.host if request.client else None)
    await touch_login(db, uid)
    return TokenPair(access_token=at, refresh_token=rt)

@router.post("/signin", response_model=TokenPair)
async def signin(req: SignReq, request: Request):
    db = get_db()
    u = await find_user_by_email(db, req.email)
    if not u or not verify_password(req.password, u["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    uid = str(u["_id"])
    at = create_access_token(uid)
    rt, exp = create_refresh_token(uid)
    await insert_refresh_token(db, uid, rt, exp, request.headers.get("user-agent"), request.client.host if request.client else None)
    await touch_login(db, uid)
    return TokenPair(access_token=at, refresh_token=rt)

class RefreshReq(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshReq, request: Request):
    db = get_db()
    # check server-side record
    rec = await is_valid_refresh(db, req.refresh_token)
    if not rec:
        raise HTTPException(401, "Invalid refresh")
    # check JWT validity
    try:
        payload = jwt.get_unverified_claims(req.refresh_token)
    except JWTError:
        raise HTTPException(401, "Invalid refresh")
    uid = str(rec["user_id"])
    at = create_access_token(uid)
    rt, exp = create_refresh_token(uid)
    # rotate: revoke old, insert new
    await revoke_token(db, req.refresh_token)
    await insert_refresh_token(db, uid, rt, exp, request.headers.get("user-agent"), request.client.host if request.client else None)
    return TokenPair(access_token=at, refresh_token=rt)

@router.post("/logout")
async def logout(req: RefreshReq):
    db = get_db()
    await revoke_token(db, req.refresh_token)
    return {"ok": True}

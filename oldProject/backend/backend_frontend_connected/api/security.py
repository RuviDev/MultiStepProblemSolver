import os, time, uuid
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext

PWD_SCHEME = os.getenv("PASSWORD_HASH_SCHEME", "bcrypt")
pwd_context = CryptContext(schemes=[PWD_SCHEME], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "change_me")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
ACCESS_TTL = int(os.getenv("JWT_ACCESS_TTL_MIN", "15")) * 60
REFRESH_TTL = int(os.getenv("JWT_REFRESH_TTL_DAYS", "7")) * 24 * 3600

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def _now() -> int:
    return int(time.time())

def create_access_token(sub: str, extra: Optional[Dict[str, Any]]=None) -> str:
    now = _now()
    payload = {"sub": sub, "iat": now, "exp": now + ACCESS_TTL, "typ": "access"}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def create_refresh_token(sub: str, jti: Optional[str]=None) -> str:
    now = _now()
    payload = {"sub": sub, "iat": now, "exp": now + REFRESH_TTL, "typ": "refresh", "jti": jti or str(uuid.uuid4())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

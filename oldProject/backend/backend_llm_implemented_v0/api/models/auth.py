from pydantic import BaseModel, EmailStr, Field

class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)

class SigninIn(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

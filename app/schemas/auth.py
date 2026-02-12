"""
Auth schemas for request/response models
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    user_name: str
    full_name: str
    phone: Optional[str] = ""


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    user_id: int
    email: str
    user_name: str
    full_name: str
    phone: Optional[str] = None
    loyalty_points: int = 0


class AuthError(BaseModel):
    detail: str

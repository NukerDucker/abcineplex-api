from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import date


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class RegisterResponse(BaseModel):
    message: str
    user_id: str
    token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenUser(BaseModel):
    id: str
    email: str
    first_name: str
    membership_tier: str
    reward_points: int


class LoginResponse(BaseModel):
    token: str
    refresh_token: str
    user: TokenUser


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    token: str
    refresh_token: str


# Kept for backward-compat with security layer that still reads full_name / loyalty_points
class UserResponse(BaseModel):
    user_id: str
    email: str
    user_name: str
    full_name: str
    loyalty_points: int = 0
    is_admin: bool = False

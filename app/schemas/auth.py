from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import date

_PASSWORD_MIN_MSG = "Password must be at least 8 characters"


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
            raise ValueError(_PASSWORD_MIN_MSG)
        return v


class SetPasswordRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError(_PASSWORD_MIN_MSG)
        return v


class SetupInfoRequest(BaseModel):
    """Used by OAuth users to complete their profile on first sign-in."""
    password: str
    user_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError(_PASSWORD_MIN_MSG)
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenUser(BaseModel):
    id: str
    email: str
    user_name: str
    first_name: str
    last_name: str
    is_admin: bool
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    is_student: bool = False
    student_id_verified: bool = False
    membership_tier: str = "free"
    reward_points: int
    attendance_streak: int = 0
    has_password: bool = True


class RegisterResponse(BaseModel):
    message: str
    # Populated when email confirmation is not required (auto-login)
    token: Optional[str] = None
    refresh_token: Optional[str] = None
    user: Optional[TokenUser] = None
    requires_confirmation: bool = False


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

"""
Auth schemas for response models.
Authentication is handled by Supabase Auth on the client side.
"""
from pydantic import BaseModel
from typing import Optional


class UserResponse(BaseModel):
    user_id: int
    email: str
    user_name: str
    full_name: str
    phone: Optional[str] = None
    loyalty_points: int = 0


class AuthError(BaseModel):
    detail: str

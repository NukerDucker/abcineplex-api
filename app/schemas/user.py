from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserResponse(BaseModel):
    user_id: str
    email: str
    user_name: str
    full_name: str
    phone: Optional[str] = None
    loyalty_points: int = 0
    is_admin: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Fields a user can update on their own profile"""
    full_name: Optional[str] = None
    user_name: Optional[str] = None
    phone: Optional[str] = None


class AdminUserUpdate(UserUpdate):
    """Additional fields only admins can update"""
    email: Optional[str] = None
    loyalty_points: Optional[int] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
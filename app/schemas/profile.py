from pydantic import BaseModel, HttpUrl
from uuid import UUID
from typing import Optional
from datetime import datetime

class ProfileBase(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[HttpUrl] = None

class ProfileUpdate(ProfileBase):
    pass

class Profile(ProfileBase):
    id: UUID
    loyalty_points: int
    updated_at: datetime

    class Config:
        from_attributes = True
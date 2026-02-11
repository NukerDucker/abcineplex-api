from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional

class ShowtimeBase(BaseModel):
    movie_id: UUID
    screen_name: str
    start_time: datetime
    # Using Field for extra validation (price cannot be negative)
    base_price: float = Field(..., ge=0)

class ShowtimeCreate(ShowtimeBase):
    """Used for POST requests"""
    pass

class Showtime(ShowtimeBase):
    """Used for GET responses"""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
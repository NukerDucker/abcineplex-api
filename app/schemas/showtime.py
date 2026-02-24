from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Optional


class ShowtimeBase(BaseModel):
    movie_id: int
    screen_id: int = Field(..., description="Screen ID from screens table")
    start_time: datetime
    base_price: float = Field(..., ge=0, description="Base price per ticket")


class ShowtimeCreate(ShowtimeBase):
    """Used for POST requests"""
    pass


class ShowtimeUpdate(BaseModel):
    movie_id: Optional[int] = None
    screen_id: Optional[int] = None
    start_time: Optional[datetime] = None
    base_price: Optional[float] = Field(None, ge=0)


class Showtime(ShowtimeBase):
    """Used for GET responses"""
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

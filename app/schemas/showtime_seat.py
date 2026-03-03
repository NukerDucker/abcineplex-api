"""Schema for showtime-specific seat configurations"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ShowtimeSeatCreate(BaseModel):
    """Create a showtime-specific seat configuration"""
    showtime_id: int
    seat_id: int
    is_available: bool = True


class ShowtimeSeatUpdate(BaseModel):
    """Update showtime seat availability"""
    is_available: bool


class ShowtimeSeat(BaseModel):
    """Showtime seat configuration"""
    id: int
    showtime_id: int
    seat_id: int
    is_available: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

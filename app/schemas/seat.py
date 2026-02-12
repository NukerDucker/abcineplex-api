from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ===== Seat Information Schemas =====
class SeatBase(BaseModel):
    row_label: str = Field(..., description="Row label (e.g., A, B, C)")
    seat_number: int = Field(..., gt=0, description="Seat number")


class SeatDetail(SeatBase):
    """Detailed seat information"""
    seat_id: int
    status: str  # available, reserved, sold, maintenance
    screen_id: int
    price: Optional[float] = None
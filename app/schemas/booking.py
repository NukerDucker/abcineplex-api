from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

class SeatLockBase(BaseModel):
    showtime_id: int
    screen_name: str
    row_letter: str
    seat_number: int

class BookingCreate(BaseModel):
    email: EmailStr
    phone: str
    showtime_id: int
    total_amount: float
    is_student_ticket: bool = False
    selected_seats: list[SeatLockBase] # To lock seats during booking creation

class Booking(BaseModel):
    id: str
    booking_ref: str
    payment_status: str
    booking_status: str
    points_earned: int
    created_at: datetime
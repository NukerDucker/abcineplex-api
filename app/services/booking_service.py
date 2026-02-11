from app.core.supabase import supabase
from datetime import datetime, timedelta

def lock_seats(booking_ref: str, showtime_id: int, seats: list[SeatLockBase]):
    expiry = (datetime.now() + timedelta(minutes=5)).isoformat()

    lock_data = []
    for seat in seats:
        lock_data.append({
            "booking_ref": booking_ref,
            "showtime_id": showtime_id,
            "screen_name": seat.screen_name,
            "row_letter": seat.row_letter,
            "seat_number": seat.seat_number,
            "status": "reserved",
            "expires_at": expiry
        })

    # Using .upsert() helps if the user refreshes and tries to lock the same seats
    response = supabase.table("seat_locks").upsert(lock_data).execute()
    return response.data
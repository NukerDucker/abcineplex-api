from supabase import Client
from typing import List, Optional
from datetime import datetime

class CRUDShowtime:
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def get_by_movie(self, movie_id: int) -> List[dict]:
        response = self.client.table("showtimes")\
            .select("*")\
            .eq("movie_id", movie_id)\
            .order("show_datetime")\
            .execute()
        return response.data

    async def get_by_id(self, showtime_id: int) -> Optional[dict]:
        response = self.client.table("showtimes")\
            .select("*")\
            .eq("showtime_id", showtime_id)\
            .single()\
            .execute()
        return response.data

    async def get_seats(self, showtime_id: int) -> List[dict]:
        # 1. Get showtime info to know the screen
        showtime = await self.get_by_id(showtime_id)
        if not showtime:
            return []

        screen_name = showtime["screen_name"]
        base_price = float(showtime["base_price"])

        # 2. Get all seats for this screen
        seats_response = self.client.table("seats")\
            .select("*")\
            .eq("screen_name", screen_name)\
            .execute()
        all_seats = seats_response.data

        # 3. Get booked seats for this showtime
        # Need to join with bookings to filter by showtime_id
        # We can use Supabase's resource embedding if the relationship is defined
        booked_response = self.client.table("booking_seats")\
            .select("row_letter, seat_number, bookings!inner(showtime_id)")\
            .eq("bookings.showtime_id", showtime_id)\
            .execute()
        booked_seats = {(s["row_letter"], s["seat_number"]) for s in booked_response.data}

        # 4. Get locked seats for this showtime
        locked_response = self.client.table("seat_locks")\
            .select("row_letter, seat_number")\
            .eq("showtime_id", showtime_id)\
            .gte("expires_at", datetime.now().isoformat())\
            .execute()
        locked_seats = {(s["row_letter"], s["seat_number"]) for s in locked_response.data}

        # 5. Map status to seats
        results = []
        for seat in all_seats:
            pos = (seat["row_letter"], seat["seat_number"])
            status = "available"
            if pos in booked_seats:
                status = "booked"
            elif pos in locked_seats:
                status = "locked"

            results.append({
                "row_letter": seat["row_letter"],
                "seat_number": seat["seat_number"],
                "seat_type": seat["seat_type"],
                "status": status,
                "price": base_price # Simplify price logic for now
            })

        return results

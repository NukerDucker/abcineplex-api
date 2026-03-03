from supabase import Client
from typing import List, Optional, Dict, Any, cast
from app.schemas.showtime import ShowtimeCreate, ShowtimeUpdate
from datetime import datetime, timezone, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)


class CRUDShowtime:
    """Optimized showtime CRUD operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create(self, showtime: ShowtimeCreate) -> dict:
        """Create a new showtime.
        - Auto-calculates end_time from movie runtime + credits.
        - Auto-fills audio_language / subtitle_language from movie if not supplied.
        - Enforces a 30-minute gap between end of one show and start of the next
          in the same theatre.
        """
        new_start: datetime = showtime.start_time
        BUFFER = timedelta(minutes=30)

        # --- Fetch movie for runtime, credits, and default languages ---------
        movie_resp = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .select("runtime_minutes, duration_minutes, credits_duration_minutes, audio_languages, subtitle_languages")
                .eq("id", showtime.movie_id)
                .maybe_single()
                .execute()
        )
        movie = movie_resp.data or {}
        runtime: int = int(movie.get("runtime_minutes") or movie.get("duration_minutes") or 120)
        credits_min: int = int(movie.get("credits_duration_minutes") or 5)
        new_end: datetime = new_start + timedelta(minutes=runtime + credits_min)

        # Default languages from movie if admin did not specify
        audio_lang = showtime.audio_language
        subtitle_lang = showtime.subtitle_language
        if not audio_lang:
            audio_langs = movie.get("audio_languages") or []
            audio_lang = audio_langs[0] if audio_langs else None
        if not subtitle_lang:
            sub_langs = movie.get("subtitle_languages") or []
            subtitle_lang = sub_langs[0] if sub_langs else None

        # --- 30-minute spacing conflict check --------------------------------
        # Fetch any showtime in a broad window that could overlap
        window_start = (new_start - timedelta(hours=12)).isoformat()
        window_end = (new_end + timedelta(hours=12)).isoformat()

        existing_resp = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("id, start_time, end_time")
                .eq("theatre_id", showtime.theatre_id)
                .eq("is_active", True)
                .gte("start_time", window_start)
                .lte("start_time", window_end)
                .execute()
        )
        for row in (existing_resp.data or []):
            ex_start_raw = row.get("start_time")
            ex_end_raw = row.get("end_time")
            if not ex_start_raw:
                continue
            ex_start = datetime.fromisoformat(str(ex_start_raw).replace("Z", "+00:00"))
            if ex_start.tzinfo is None:
                ex_start = ex_start.replace(tzinfo=None)
            if ex_end_raw:
                ex_end = datetime.fromisoformat(str(ex_end_raw).replace("Z", "+00:00"))
                if ex_end.tzinfo is None:
                    ex_end = ex_end.replace(tzinfo=None)
            else:
                ex_end = ex_start + timedelta(hours=3)  # fallback estimate

            # Overlap check with 30-min buffer:
            # New show window: [new_start, new_end + BUFFER]
            # Existing show window: [ex_start - BUFFER, ex_end]
            # Conflict if: new_start < ex_end + BUFFER  AND  new_end + BUFFER > ex_start
            if new_start < (ex_end + BUFFER) and (new_end + BUFFER) > ex_start:
                raise ValueError(
                    f"Showtime conflicts: must be at least 30 minutes after the show ending at "
                    f"{ex_end.strftime('%H:%M')} in the same theatre."
                )

        # --- Build insert payload ---------------------------------------------
        data = showtime.model_dump(mode='json')
        data["end_time"] = new_end.isoformat()
        data["audio_language"] = audio_lang
        data["subtitle_language"] = subtitle_lang
        # Also write legacy language field (first audio lang)
        if not data.get("language"):
            data["language"] = audio_lang

        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes").insert(data).execute()
        )
        return response.data[0]

    async def update(self, showtime_id: int, showtime_in: ShowtimeUpdate) -> Optional[dict]:
        """Update showtime with fallback"""
        data = showtime_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(showtime_id)

        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .update(data)
                .eq("id", showtime_id)
                .execute()
        )
        return response.data[0]

    async def delete(self, showtime_id: int) -> bool:
        """Delete a showtime"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes").delete().eq("id", showtime_id).execute()
        )
        return bool(response.data)

    async def get_by_movie(self, movie_id: int) -> List[dict]:
        """Get all showtimes for a movie"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("movie_id", movie_id)
                .order("start_time")
                .execute()
        )
        return response.data or []

    async def get_by_id(self, showtime_id: int) -> Optional[dict]:
        """Get showtime by ID with safe fallback"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("id", showtime_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_seats_for_screen(self, theatre_id: int, base_price: float) -> List[Dict[str, Any]]:
        """
        Get all seats for a screen with availability status.
        Optimized with single query and list comprehension for memory efficiency.
        """
        response = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("id, row_label, seat_number, status")
                .eq("theatre_id", theatre_id)
                .order("row_label")
                .order("seat_number")
                .execute()
        )

        if not response.data:
            return []

        # Memory-efficient list comprehension instead of loop
        return [
            {
                "seat_id": seat["id"],
                "row_label": seat["row_label"],
                "seat_number": seat["seat_number"],
                "status": seat["status"],
                "price": base_price
            }
            for seat in response.data
        ]

    async def get_detail(self, showtime_id: int) -> Optional[Dict[str, Any]]:
        """Get a showtime with movie and screen joined — for GET /showtimes/:id."""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select(
                    "*, "
                    "movies(id, title, duration_minutes, imdb_score, rating_count, release_date, credits_duration_minutes)"
                )
                .eq("id", showtime_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_seat_map(self, theatre_id: int, showtime_id: int) -> List[Dict[str, Any]]:
        """Get seat map with per-showtime availability.

        Status is computed dynamically:
          - disabled : seat.is_active == false
          - booked   : linked to a confirmed booking for THIS showtime
          - held     : linked to a pending booking for THIS showtime
          - available: everything else
        """
        # 1. All seats in this theatre
        seats_resp = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("id, row_label, seat_number, seat_type, is_active")
                .eq("theatre_id", theatre_id)
                .order("row_label")
                .order("seat_number")
                .execute()
        )
        all_seats: List[Dict[str, Any]] = cast(List[Dict[str, Any]], seats_resp.data or [])

        # 2. Active bookings (pending + confirmed) for this specific showtime
        bookings_resp = await asyncio.to_thread(
            lambda: self.client.table("bookings")
                .select("id, booking_status, payment_deadline")
                .eq("showtime_id", showtime_id)
                .in_("booking_status", ["pending", "confirmed"])
                .execute()
        )
        bookings: List[Dict[str, Any]] = cast(List[Dict[str, Any]], bookings_resp.data or [])
        now = datetime.now(timezone.utc)

        def _not_expired(b: Dict[str, Any]) -> bool:
            raw = b.get("payment_deadline")
            if not raw:
                return False
            dl = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            return dl > now

        pending_ids: set[str] = {
            str(b["id"]) for b in bookings
            if b["booking_status"] == "pending" and _not_expired(b)
        }
        confirmed_ids: set[str] = {str(b["id"]) for b in bookings if b["booking_status"] == "confirmed"}
        all_booking_ids: List[str] = list(pending_ids | confirmed_ids)

        # 3. Which seats belong to those bookings
        held_seat_ids: set[int] = set()
        booked_seat_ids: set[int] = set()
        if all_booking_ids:
            bs_resp = await asyncio.to_thread(
                lambda: self.client.table("booking_seats")
                    .select("seat_id, booking_id")
                    .in_("booking_id", all_booking_ids)
                    .execute()
            )
            for bs in cast(List[Dict[str, Any]], bs_resp.data or []):
                seat_id = int(bs["seat_id"])
                booking_id = str(bs["booking_id"])
                if booking_id in confirmed_ids:
                    booked_seat_ids.add(seat_id)
                elif booking_id in pending_ids:
                    held_seat_ids.add(seat_id)

        # 4. Build result with computed status
        result: List[Dict[str, Any]] = []
        for seat in all_seats:
            sid = int(seat["id"])
            if not seat.get("is_active", True):
                computed = "disabled"
            elif sid in booked_seat_ids:
                computed = "booked"
            elif sid in held_seat_ids:
                computed = "held"
            else:
                computed = "available"

            result.append({
                "id": sid,
                "row_label": str(seat["row_label"]).strip(),
                "seat_number": int(seat["seat_number"]),
                "seat_type": str(seat.get("seat_type") or "standard"),
                "status": computed,
            })

        return result

    async def get_screen_occupancy(self, theatre_id: int) -> Dict[str, Any]:
        """Count active seats for a theatre directly from the seats table."""
        try:
            resp = await asyncio.to_thread(
                lambda: self.client.table("seats")
                    .select("id", count="exact")
                    .eq("theatre_id", theatre_id)
                    .eq("is_active", True)
                    .execute()
            )
            count = resp.count or 0
            return {"theatre_id": theatre_id, "total_seats": count, "available_seats": count}
        except Exception as e:
            logger.error(f"Error getting occupancy for screen {theatre_id}: {e}")
            return {"theatre_id": theatre_id, "total_seats": 0, "available_seats": 0}

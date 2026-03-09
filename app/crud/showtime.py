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

        # --- Fetch movie for runtime and credits ---------
        movie_resp = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .select("runtime_minutes, duration_minutes, credits_duration_minutes")
                .eq("id", showtime.movie_id)
                .limit(1)
                .execute()
        )
        movie = (movie_resp.data or [None])[0] or {}
        runtime: int = int(movie.get("runtime_minutes") or movie.get("duration_minutes"))
        credits_min: int = int(movie.get("credits_duration_minutes") or 5)
        new_end: datetime = new_start + timedelta(minutes=runtime + credits_min)

        # Default languages from junction tables if admin did not specify
        audio_lang = showtime.audio_language
        subtitle_lang = showtime.subtitle_language
        if not audio_lang:
            audio_resp = await asyncio.to_thread(
                lambda: self.client.table("movie_audio_languages")
                    .select("language")
                    .eq("movie_id", showtime.movie_id)
                    .limit(1)
                    .execute()
            )
            audio_rows: List[Dict[str, Any]] = audio_resp.data or []
            audio_lang = audio_rows[0]["language"] if audio_rows else None
        if not subtitle_lang:
            sub_resp = await asyncio.to_thread(
                lambda: self.client.table("movie_subtitle_languages")
                    .select("language")
                    .eq("movie_id", showtime.movie_id)
                    .limit(1)
                    .execute()
            )
            sub_rows: List[Dict[str, Any]] = sub_resp.data or []
            subtitle_lang = sub_rows[0]["language"] if sub_rows else None

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
        showtime_record = response.data[0]

        # Auto-populate showtime_seats for all theatre seats
        try:
            # Fetch all seats for this theatre
            seats_response = await asyncio.to_thread(
                lambda: self.client.table("seats")
                    .select("id")
                    .eq("theatre_id", showtime.theatre_id)
                    .execute()
            )
            seat_ids = [row['id'] for row in (seats_response.data or [])]

            if seat_ids:
                showtime_seats_data = [
                    {
                        "showtime_id": showtime_record['id'],
                        "seat_id": seat_id,
                        "is_available": True
                    }
                    for seat_id in seat_ids
                ]

                await asyncio.to_thread(
                    lambda: self.client.table("showtime_seats").insert(showtime_seats_data).execute()
                )
                logger.info(f"Created {len(showtime_seats_data)} showtime seats for showtime {showtime_record['id']}")
        except Exception as e:
            logger.error(f"Failed to create showtime_seats for showtime {showtime_record['id']}: {e}")

        return showtime_record

    async def update(self, showtime_id: int, showtime_in: ShowtimeUpdate) -> Optional[dict]:
        """Update showtime. Auto-recalculates end_time when start_time changes.
        Validates that the new start_time is in the future and doesn't conflict
        with other showtimes in the same theatre (30-minute gap required).
        """
        data = showtime_in.model_dump(exclude_unset=True, mode='json')
        if not data:
            return await self.get_by_id(showtime_id)

        # Recalculate end_time and validate conflicts when start_time is being changed
        if "start_time" in data:
            new_start = datetime.fromisoformat(str(data["start_time"]).replace("Z", "+00:00"))
            if new_start.tzinfo is None:
                new_start = new_start.replace(tzinfo=timezone.utc)

            # Must be in the future
            now = datetime.now(tz=timezone.utc)
            if new_start <= now:
                raise ValueError("start_time must be in the future.")

            current = await asyncio.to_thread(
                lambda: self.client.table("showtimes")
                    .select("movie_id, theatre_id")
                    .eq("id", showtime_id)
                    .maybe_single()
                    .execute()
            )
            current_data = current.data or {}
            movie_id = current_data.get("movie_id")
            theatre_id = current_data.get("theatre_id")

            if movie_id:
                movie_resp = await asyncio.to_thread(
                    lambda: self.client.table("movies")
                        .select("runtime_minutes, duration_minutes, credits_duration_minutes")
                        .eq("id", movie_id)
                        .limit(1)
                        .execute()
                )
                movie = (movie_resp.data or [{}])[0]
                runtime = int(movie.get("runtime_minutes") or movie.get("duration_minutes") or 0)
                credits_min = int(movie.get("credits_duration_minutes") or 5)
                new_end = new_start + timedelta(minutes=runtime + credits_min)
                data["end_time"] = new_end.isoformat()

                # Check theatre conflict with 30-minute buffer (exclude self)
                if theatre_id:
                    BUFFER = timedelta(minutes=30)
                    window_start = (new_start - timedelta(hours=12)).isoformat()
                    window_end = (new_end + timedelta(hours=12)).isoformat()
                    existing_resp = await asyncio.to_thread(
                        lambda: self.client.table("showtimes")
                            .select("id, start_time, end_time")
                            .eq("theatre_id", theatre_id)
                            .eq("is_active", True)
                            .gte("start_time", window_start)
                            .lte("start_time", window_end)
                            .execute()
                    )
                    for row in (existing_resp.data or []):
                        if row.get("id") == showtime_id:
                            continue  # skip self
                        ex_start_raw = row.get("start_time")
                        ex_end_raw = row.get("end_time")
                        if not ex_start_raw:
                            continue
                        ex_start = datetime.fromisoformat(str(ex_start_raw).replace("Z", "+00:00"))
                        if ex_start.tzinfo is None:
                            ex_start = ex_start.replace(tzinfo=timezone.utc)
                        if ex_end_raw:
                            ex_end = datetime.fromisoformat(str(ex_end_raw).replace("Z", "+00:00"))
                            if ex_end.tzinfo is None:
                                ex_end = ex_end.replace(tzinfo=timezone.utc)
                        else:
                            ex_end = ex_start + timedelta(hours=3)

                        if new_start < (ex_end + BUFFER) and (new_end + BUFFER) > ex_start:
                            raise ValueError(
                                f"Showtime conflicts: must be at least 30 minutes after the show ending at "
                                f"{ex_end.strftime('%H:%M')} in the same theatre."
                            )

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
        """Get all showtimes for a movie (all dates)"""
        response = await asyncio.to_thread(
            lambda: self.client.table("showtimes")
                .select("*")
                .eq("movie_id", movie_id)
                .eq("is_active", True)
                .order("start_time")
                .execute()
        )
        return response.data or []

    async def get_all_active_showtimes(self, is_active: Optional[bool] = None) -> List[dict]:
        """Get ALL showtimes from database (active or all).
        Use for bulk operations or bulk filtering on frontend.

        Args:
            is_active: None = all showtimes, True = active only, False = inactive only
        """
        query = self.client.table("showtimes").select("*")

        if is_active is not None:
            query = query.eq("is_active", is_active)

        query = query.gte("start_time", datetime.now(timezone.utc).isoformat())
        query = query.order("start_time")

        response = await asyncio.to_thread(lambda: query.execute())
        return response.data or []

    async def get_showtimes_by_movie_and_date(
        self,
        movie_id: int,
        from_date: str,
        to_date: str,
        is_active: Optional[bool] = True,
    ) -> List[dict]:
        """Optimized: Get showtimes for movie within date range.
        All filtering done at database level.

        Args:
            movie_id: Movie ID to filter by
            from_date: Start date (ISO format string)
            to_date: End date (ISO format string)
            is_active: None = all showtimes, True = active only, False = inactive only (default: True)
        """
        query = self.client.table("showtimes").select("*, theatres(name)")
        query = query.eq("movie_id", movie_id)

        if is_active is not None:
            query = query.eq("is_active", is_active)

        query = query.gte("start_time", from_date)
        query = query.lte("start_time", to_date)
        query = query.order("start_time")

        response = await asyncio.to_thread(lambda: query.execute())
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
                    "movies(id, title, duration_minutes, imdb_score, rating_count, release_date, credits_duration_minutes), "
                    "theatres(name, total_seats)"
                )
                .eq("id", showtime_id)
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_seat_map(self, theatre_id: int, showtime_id: int) -> List[Dict[str, Any]]:
        """Get seat map with per-showtime availability.

        Status is computed dynamically:
          - disabled : seat.is_active == false OR showtime_seats.is_available == false
          - booked   : linked to a confirmed booking for THIS showtime
          - held     : linked to a pending booking for THIS showtime
          - available: everything else
        """
        # 1. All seats in this theatre with their showtime-specific availability
        seats_resp = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("id, row_label, seat_number, is_active")
                .eq("theatre_id", theatre_id)
                .order("row_label")
                .order("seat_number")
                .execute()
        )
        all_seats: List[Dict[str, Any]] = cast(List[Dict[str, Any]], seats_resp.data or [])

        # 2. Get showtime_seats for this specific showtime
        showtime_seats_resp = await asyncio.to_thread(
            lambda: self.client.table("showtime_seats")
                .select("seat_id, is_available")
                .eq("showtime_id", showtime_id)
                .execute()
        )
        showtime_seats_data: List[Dict[str, Any]] = cast(List[Dict[str, Any]], showtime_seats_resp.data or [])
        showtime_seat_availability: dict[int, bool] = {
            int(ss["seat_id"]): bool(ss["is_available"]) for ss in showtime_seats_data
        }

        # 3. Active bookings (pending + confirmed) for this specific showtime
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

        # 4. Which seats belong to those bookings
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

        # 5. Build result with computed status
        result: List[Dict[str, Any]] = []
        for seat in all_seats:
            sid = int(seat["id"])
            # Check all disable conditions
            is_seat_disabled = not seat.get("is_active", True)
            is_showtime_unavailable = not showtime_seat_availability.get(sid, True)

            if is_seat_disabled:
                computed = "disabled"
            elif sid in booked_seat_ids:
                # Confirmed booking takes priority — even if RPC set is_available=false
                computed = "booked"
            elif sid in held_seat_ids:
                computed = "held"
            elif is_showtime_unavailable:
                # Admin-blocked seat (no booking exists)
                computed = "disabled"
            else:
                computed = "available"

            result.append({
                "id": sid,
                "row_label": str(seat["row_label"]).strip(),
                "seat_number": int(seat["seat_number"]),
                "status": computed,
            })

        return result

    async def get_showtime_availability(self, showtime_id: int) -> int:
        """Return number of seats available for booking for a given showtime.

        available = showtime_seats.is_available=true minus active seat_holds (not expired).
        This matches the CLAUDE.md predictive demand badge spec.
        """
        def fetch():
            available_res = self.client.table("showtime_seats").select("seat_id", count="exact").eq("showtime_id", showtime_id).eq("is_available", True).execute()
            holds_res = self.client.table("seat_holds").select("seat_id", count="exact").eq("showtime_id", showtime_id).gt("hold_expires_at", "now()").execute()
            return (available_res.count or 0), (holds_res.count or 0)

        try:
            available_count, hold_count = await asyncio.to_thread(fetch)
            return max(0, available_count - hold_count)
        except Exception as e:
            logger.error(f"Error getting showtime availability for {showtime_id}: {e}")
            return 0

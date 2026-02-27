"""
Booking CRUD — all write operations go through PostgreSQL RPC functions
for atomicity. Read operations use direct table/view queries.
"""
from typing import Any, Dict, List, Optional
from supabase import Client
from app.schemas.booking import (
    BookingDetail,
    ReserveSeatRequest,
    AvailableSeat,
    ScreenInfo,
)
import logging
import asyncio

logger = logging.getLogger(__name__)


class CRUDBooking:

    def __init__(self, client: Client):
        self.client = client

    # ── Helpers ───────────────────────────────────────────────

    async def _rpc(self, fn: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a Supabase RPC function and return its JSONB result."""
        response = await asyncio.to_thread(
            lambda: self.client.rpc(fn, params).execute()
        )
        # The RPC returns the JSONB value directly in response.data
        return response.data or {}

    # ── Write operations (via RPC) ────────────────────────────

    async def reserve_seats(self, request: ReserveSeatRequest, user_id: str) -> Dict[str, Any]:
        """Create a pending booking with a 5-minute hold. Atomic — no race conditions."""
        return await self._rpc("reserve_seats", {
            "p_user_id":        str(user_id),
            "p_showtime_id":    request.showtime_id,
            "p_seat_ids":       request.seat_ids,
            "p_price_per_seat": request.price_per_seat,
            "p_ticket_type":    request.ticket_type,
        })

    async def confirm_payment(self, booking_id: str, payment_intent_id: Optional[str] = None) -> Dict[str, Any]:
        """Confirm payment: sets booking to confirmed and issues tickets."""
        return await self._rpc("confirm_booking_payment", {
            "p_booking_id":     str(booking_id),
            "p_payment_method": payment_intent_id or "mock_card",
        })

    async def cancel_booking(self, booking_id: str) -> Dict[str, Any]:
        """Cancel a booking. No refund. Idempotent."""
        return await self._rpc("cancel_booking", {
            "p_booking_id": str(booking_id),
        })

    async def release_expired_reservations(self) -> Dict[str, Any]:
        """Cancel all pending bookings whose 5-minute hold has expired."""
        return await self._rpc("release_expired_reservations", {})

    # ── Read operations (direct table/view queries) ───────────

    async def get_booking_by_id(self, booking_id: str) -> Optional[Dict[str, Any]]:
        """Fetch raw booking row by UUID. Returns None if not found."""
        try:
            res = await asyncio.to_thread(
                lambda: self.client.table("bookings")
                    .select("*")
                    .eq("id", str(booking_id))
                    .single()
                    .execute()
            )
            return res.data or None
        except Exception:
            return None

    async def get_booking_details(self, booking_id: str) -> Optional[BookingDetail]:
        """Fetch enriched booking detail (movie, theatre, seats, QR codes)."""
        try:
            res = await asyncio.to_thread(
                lambda: self.client.from_("booking_details")
                    .select("*")
                    .eq("booking_id", str(booking_id))
                    .single()
                    .execute()
            )
            if not res.data:
                return None
            data: Dict[str, Any] = dict(res.data)

            # Attach tickets if confirmed
            if data.get("booking_status") == "confirmed":
                tickets = await self.get_tickets_for_booking(booking_id)
                data["tickets"] = tickets or None
                if tickets:
                    data["qr_code_data"] = ",".join(
                        t["qr_code_slug"] for t in tickets if t.get("qr_code_slug")
                    ) or None

            return BookingDetail(**data)
        except Exception as e:
            logger.error(f"get_booking_details error: {e}")
            return None

    async def get_user_bookings(self, user_id: str, status: Optional[str] = None) -> List[BookingDetail]:
        """All bookings for a user, newest first."""
        try:
            def _fetch():
                q = (
                    self.client.from_("booking_details")
                    .select("*")
                    .eq("user_id", str(user_id))
                    .order("created_at", desc=True)
                )
                if status:
                    q = q.eq("booking_status", status)
                return q.execute()

            res = await asyncio.to_thread(_fetch)
            return [BookingDetail(**row) for row in (res.data or [])]
        except Exception as e:
            logger.error(f"get_user_bookings error: {e}")
            return []

    async def get_tickets_for_booking(self, booking_id: str) -> List[Dict[str, Any]]:
        """All tickets for a booking, with seat labels."""
        try:
            res = await asyncio.to_thread(
                lambda: self.client.table("tickets")
                    .select("*, seats(row_label, seat_number)")
                    .eq("booking_id", str(booking_id))
                    .execute()
            )
            tickets = []
            for t in (res.data or []):
                seat = t.get("seats") or {}
                tickets.append({
                    "ticket_id":    t["id"],
                    "booking_id":   t["booking_id"],
                    "seat_id":      t["seat_id"],
                    "price_paid":   t["price_paid"],
                    "qr_code_slug": t["qr_code_slug"],
                    "row_label":    seat.get("row_label", ""),
                    "seat_number":  seat.get("seat_number", 0),
                })
            return tickets
        except Exception as e:
            logger.error(f"get_tickets_for_booking error: {e}")
            return []

    # ── Admin operations ──────────────────────────────────────

    async def update_booking_status(self, booking_id: str, status: str) -> Optional[Dict[str, Any]]:
        """Admin: directly update booking status."""
        try:
            res = await asyncio.to_thread(
                lambda: self.client.table("bookings")
                    .update({"booking_status": status})
                    .eq("id", str(booking_id))
                    .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"update_booking_status error: {e}")
            raise

    async def get_all_bookings(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Admin: list all bookings with optional status filter."""
        try:
            def _fetch():
                q = (
                    self.client.table("bookings")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .offset(offset)
                )
                if status:
                    q = q.eq("booking_status", status)
                return q.execute()

            res = await asyncio.to_thread(_fetch)
            return res.data or []
        except Exception as e:
            logger.error(f"get_all_bookings error: {e}")
            raise

    async def get_pending_bookings_count(self) -> int:
        """Count of currently pending bookings (active holds)."""
        try:
            res = await asyncio.to_thread(
                lambda: self.client.table("bookings")
                    .select("id", count="exact")
                    .eq("booking_status", "pending")
                    .execute()
            )
            return res.count or 0
        except Exception:
            return 0

    # ── Legacy screen endpoints (kept for /bookings/screens) ──

    async def get_all_seats_for_screen(self, theatre_id: int) -> List[Dict[str, Any]]:
        res = await asyncio.to_thread(
            lambda: self.client.table("seats")
                .select("*")
                .eq("theatre_id", theatre_id)
                .order("row_label").order("seat_number")
                .execute()
        )
        return res.data or []

    async def get_available_seats(self, theatre_id: int) -> List[AvailableSeat]:
        rows = await self.get_all_seats_for_screen(theatre_id)
        return [
            AvailableSeat(
                seat_id=r["id"],
                row_label=r["row_label"].strip(),
                seat_number=r["seat_number"],
                status="available" if r.get("is_active", True) else "disabled",
            )
            for r in rows
        ]

    async def get_all_screens(self) -> List[ScreenInfo]:
        res = await asyncio.to_thread(
            lambda: self.client.table("theatres").select("*").execute()
        )
        return [
            ScreenInfo(theatre_id=r["id"], name=r["name"], total_seats=r["total_seats"])
            for r in (res.data or [])
        ]

    async def get_screen_by_id(self, theatre_id: int) -> Optional[ScreenInfo]:
        try:
            res = await asyncio.to_thread(
                lambda: self.client.table("theatres")
                    .select("*")
                    .eq("id", theatre_id)
                    .single()
                    .execute()
            )
            if res.data:
                r = res.data
                return ScreenInfo(theatre_id=r["id"], name=r["name"], total_seats=r["total_seats"])
            return None
        except Exception:
            return None


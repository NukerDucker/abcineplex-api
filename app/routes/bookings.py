"""
Booking API Routes
"""
from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import asyncio

from app.schemas.booking import (
    ReserveSeatRequest,
    ReserveSeatResponse,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
    CancelBookingRequest,
    CancelBookingResponse,
    ChangeShowtimeRequest,
    ChangeSeatRequest,
    BookingDetail,
    AvailableSeat,
    ScreenInfo,
    ExpiryWorkerResponse,
    GuestBookingRequest,
    GuestBookingResponse,
)
from app.crud.booking import CRUDBooking
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, get_admin_user, CurrentUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])
crud_booking = CRUDBooking(supabase_admin)

_NOT_FOUND  = "Booking not found"
_FORBIDDEN  = "Not your booking"


# ── Guest booking endpoints (no auth required) ────────────────

@router.post("/guest", response_model=GuestBookingResponse, status_code=status.HTTP_201_CREATED)
async def create_guest_booking(request: GuestBookingRequest):
    """Reserve seats for a guest (no account required). Returns a one-time token to access the booking."""
    reserve_req = ReserveSeatRequest(
        showtime_id=request.showtime_id,
        seat_ids=request.seat_ids,
        price_per_seat=request.price_per_seat,
        ticket_type=request.ticket_type,
    )
    try:
        result = await crud_booking.reserve_seats(reserve_req, user_id=None)
    except Exception as e:
        logger.error(f"guest reserve_seats failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.get("error", "Failed to reserve seats"),
        )

    booking_id = str(result["booking_id"])
    token = await crud_booking.create_guest_session(booking_id, request.email, request.phone)
    return GuestBookingResponse(
        booking_id=booking_id,
        guest_token=token,
        total_amount=result.get("total_amount", 0.0),
        payment_deadline=result.get("payment_deadline"),
    )


@router.get("/guest", response_model=BookingDetail)
async def get_guest_booking(token: str = Query(..., description="Guest session token")):
    """Retrieve a guest booking using the one-time token."""
    booking = await crud_booking.get_booking_by_guest_token(token)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found or token expired")
    return booking


# ── Create / reserve seats ────────────────────────────────────

@router.post("", response_model=ReserveSeatResponse)
async def create_booking(
    request: ReserveSeatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reserve seats and create a pending booking (5-minute hold starts)."""
    try:
        result = await crud_booking.reserve_seats(request, user_id=current_user.user_id)
    except Exception as e:
        logger.error(f"reserve_seats failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not result.get("success"):
        return ReserveSeatResponse(
            success=False,
            error=result.get("error", "Failed to reserve seats"),
            unavailable_seats=result.get("unavailable_seats"),
        )

    return ReserveSeatResponse(
        success=True,
        booking_id=str(result["booking_id"]),
        payment_deadline=result.get("payment_deadline"),
        total_amount=request.price_per_seat * len(request.seat_ids),
    )


# ── Confirm payment ───────────────────────────────────────────

@router.post("/confirm-payment", response_model=ConfirmPaymentResponse)
async def confirm_payment(
    request: ConfirmPaymentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Finalise a booking after payment succeeds."""
    booking = await crud_booking.get_booking_by_id(request.booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    if not current_user.is_admin and str(booking.get("user_id")) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)

    if booking.get("booking_status") == "confirmed":
        tickets = await crud_booking.get_tickets_for_booking(request.booking_id)
        return ConfirmPaymentResponse(
            success=True,
            message="Already confirmed",
            booking_id=request.booking_id,
            tickets=tickets,
        )

    if booking.get("booking_status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot confirm. Status: {booking.get('booking_status')}",
        )

    try:
        result = await crud_booking.confirm_payment(
            request.booking_id,
            payment_intent_id=request.payment_intent_id,
        )
    except Exception as e:
        logger.error(f"confirm_payment failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    if not result.get("success"):
        return ConfirmPaymentResponse(
            success=False,
            message=result.get("error", "Payment confirmation failed"),
        )

    tickets = await crud_booking.get_tickets_for_booking(request.booking_id)
    return ConfirmPaymentResponse(
        success=True,
        message="Payment confirmed",
        booking_id=request.booking_id,
        tickets=tickets,
    )


# ── Cancel booking ────────────────────────────────────────────

@router.post("/cancel", response_model=CancelBookingResponse)
async def cancel_booking_post(
    request: CancelBookingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel a booking (POST variant)."""
    booking = await crud_booking.get_booking_by_id(request.booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    if not current_user.is_admin and str(booking.get("user_id")) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)

    if booking.get("booking_status") == "confirmed" and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can cancel confirmed bookings",
        )

    result = await crud_booking.cancel_booking(request.booking_id)
    return CancelBookingResponse(
        success=result.get("success", False),
        message=result.get("message", result.get("error", "Cancelled")),
    )


@router.delete("/{booking_id}", response_model=CancelBookingResponse)
async def cancel_booking_delete(
    booking_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel a booking (DELETE). No refund per theatre policy."""
    booking = await crud_booking.get_booking_by_id(str(booking_id))
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    if not current_user.is_admin and str(booking.get("user_id")) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)

    if booking.get("booking_status") == "confirmed" and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can cancel confirmed bookings",
        )

    result = await crud_booking.cancel_booking(str(booking_id))
    return CancelBookingResponse(
        success=result.get("success", False),
        message="Booking cancelled. No refund per theatre policy.",
    )


# ── Get booking detail ────────────────────────────────────────

@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get full booking detail including seats and QR codes."""
    detail = await crud_booking.get_booking_details(str(booking_id))
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    if not current_user.is_admin and str(detail.user_id) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)

    return detail


@router.get("/{booking_id}/tickets")
async def get_booking_tickets(
    booking_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all tickets (with QR codes) for a confirmed booking."""
    booking = await crud_booking.get_booking_by_id(str(booking_id))
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    if not current_user.is_admin and str(booking.get("user_id")) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN)

    tickets = await crud_booking.get_tickets_for_booking(str(booking_id))
    return {"tickets": tickets}


# ── Screen / seat listing ─────────────────────────────────────

@router.get("/screens", response_model=List[ScreenInfo])
async def get_screens():
    return await crud_booking.get_all_screens()


@router.get("/screens/{theatre_id}", response_model=ScreenInfo)
async def get_screen(theatre_id: int):
    screen = await crud_booking.get_screen_by_id(theatre_id)
    if not screen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Screen not found")
    return screen


@router.get("/screens/{theatre_id}/seats", response_model=List[AvailableSeat])
async def get_available_seats(theatre_id: int):
    return await crud_booking.get_available_seats(theatre_id)


# ── Internal worker endpoint ──────────────────────────────────

@router.post("/internal/release-expired", response_model=ExpiryWorkerResponse)
async def release_expired(_: CurrentUser = Depends(get_admin_user)):
    """Release all expired seat holds. Call every minute via cron."""
    result = await crud_booking.release_expired_reservations()
    return ExpiryWorkerResponse(
        released_count=result.get("released_count", 0),
        booking_ids=result.get("booking_ids"),
        timestamp=datetime.now(),
    )


# ── Self-service: change showtime / seat ─────────────────────

@router.post("/{booking_id}/change-showtime")
async def change_showtime(
    booking_id: str,
    body: ChangeShowtimeRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Self-service showtime change (no refund; upcharge if more expensive)."""
    # Fetch booking
    booking = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("*")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    b = booking.data

    if b.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if b.get("booking_status") != "confirmed":
        raise HTTPException(status_code=400, detail="Only confirmed bookings can have their showtime changed")

    # Enforce change_count limit (1 change maximum)
    if (b.get("change_count") or 0) >= 1:
        raise HTTPException(status_code=400, detail="Showtime can only be changed once")

    # Enforce 30-min cutoff before original showtime; also fetch base_price for upcharge calc
    orig_showtime = await asyncio.to_thread(
        lambda: supabase_admin.table("showtimes")
            .select("start_time, base_price")
            .eq("id", b["showtime_id"])
            .maybe_single()
            .execute()
    )
    if orig_showtime.data:
        raw_st = orig_showtime.data.get("start_time")
        if raw_st:
            st = datetime.fromisoformat(str(raw_st).replace("Z", "+00:00"))
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) + timedelta(minutes=30) >= st:
                raise HTTPException(status_code=400, detail="Cannot change showtime within 30 minutes of screening")

    # Verify new showtime exists and is in the future
    new_st_res = await asyncio.to_thread(
        lambda: supabase_admin.table("showtimes")
            .select("id, start_time, base_price, is_active")
            .eq("id", body.new_showtime_id)
            .maybe_single()
            .execute()
    )
    if not new_st_res.data:
        raise HTTPException(status_code=404, detail="New showtime not found")

    # Check if new showtime is still active (not expired more than 40 min ago)
    if not new_st_res.data.get("is_active", False):
        raise HTTPException(status_code=400, detail="New showtime has expired and is no longer available")

    old_showtime_id = b["showtime_id"]
    update_data = {
        "showtime_id": body.new_showtime_id,
        "booking_status": "changed",
        "original_showtime_id": old_showtime_id,
        "change_count": (b.get("change_count") or 0) + 1,
    }
    await asyncio.to_thread(
        lambda: supabase_admin.table("bookings").update(update_data).eq("id", booking_id).execute()
    )

    # Capture old seat IDs before modifying booking_seats (needed to restore showtime_seats)
    old_bs_res = await asyncio.to_thread(
        lambda: supabase_admin.table("booking_seats")
            .select("seat_id")
            .eq("booking_id", booking_id)
            .execute()
    )
    old_seat_ids = [row["seat_id"] for row in (old_bs_res.data or [])]

    if body.new_seat_ids:
        await asyncio.to_thread(
            lambda: supabase_admin.table("booking_seats").delete().eq("booking_id", booking_id).execute()
        )
        new_seats = [{"booking_id": booking_id, "seat_id": sid, "showtime_id": body.new_showtime_id} for sid in body.new_seat_ids]
        await asyncio.to_thread(
            lambda: supabase_admin.table("booking_seats").insert(new_seats).execute()
        )
    else:
        # Update existing booking_seats to new showtime
        await asyncio.to_thread(
            lambda: supabase_admin.table("booking_seats")
                .update({"showtime_id": body.new_showtime_id})
                .eq("booking_id", booking_id)
                .execute()
        )

    # Restore old showtime's seats to available (the booking moved away from old_showtime_id)
    for sid in old_seat_ids:
        await asyncio.to_thread(
            lambda s=sid: supabase_admin.table("showtime_seats")
                .update({"is_available": True})
                .eq("showtime_id", old_showtime_id)
                .eq("seat_id", s)
                .execute()
        )

    # Calculate upcharge if new showtime is more expensive
    old_price = float((orig_showtime.data or {}).get("base_price") or 0)
    new_price = float(new_st_res.data.get("base_price") or 0)
    num_tickets = int(b.get("num_tickets") or 1)
    price_difference = max(0.0, (new_price - old_price) * num_tickets)

    if price_difference > 0:
        old_total = float(b.get("total_amount") or 0)
        await asyncio.to_thread(
            lambda: supabase_admin.table("bookings")
                .update({"total_amount": old_total + price_difference})
                .eq("id", booking_id)
                .execute()
        )

    return {
        "booking_id": booking_id,
        "old_showtime_id": old_showtime_id,
        "new_showtime_id": body.new_showtime_id,
        "status": "changed",
        "price_difference": price_difference,
        "message": "Showtime changed. No refund for downgrade. Additional charge applied if any.",
    }


@router.post("/{booking_id}/change-seat")
async def change_seat(
    booking_id: str,
    body: ChangeSeatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Self-service seat change within the same showtime (any time before it starts)."""
    booking = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("*")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    b = booking.data

    if b.get("user_id") != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if b.get("booking_status") not in ("confirmed", "changed"):
        raise HTTPException(status_code=400, detail="Only confirmed bookings can have seats changed")

    # Enforce showtime hasn't started yet
    showtime_res = await asyncio.to_thread(
        lambda: supabase_admin.table("showtimes")
            .select("start_time")
            .eq("id", b["showtime_id"])
            .maybe_single()
            .execute()
    )
    if showtime_res.data:
        raw_st = showtime_res.data.get("start_time")
        if raw_st:
            st = datetime.fromisoformat(str(raw_st).replace("Z", "+00:00"))
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) >= st:
                raise HTTPException(status_code=400, detail="Cannot change seats after showtime has started")

    # Get old seat IDs
    old_seats_res = await asyncio.to_thread(
        lambda: supabase_admin.table("booking_seats")
            .select("seat_id")
            .eq("booking_id", booking_id)
            .execute()
    )
    old_seat_ids = [row["seat_id"] for row in (old_seats_res.data or [])]

    # Find active bookings (by others) for this showtime to check conflicts
    other_bookings_res = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("id, booking_status, payment_deadline")
            .eq("showtime_id", b["showtime_id"])
            .neq("id", booking_id)
            .in_("booking_status", ["confirmed", "changed", "pending"])
            .execute()
    )
    now = datetime.now(timezone.utc)
    active_booking_ids = []
    for bk in (other_bookings_res.data or []):
        bk_status = bk["booking_status"]
        if bk_status in ("confirmed", "changed"):
            active_booking_ids.append(bk["id"])
        elif bk_status == "pending":
            deadline_raw = bk.get("payment_deadline")
            if deadline_raw:
                dl = datetime.fromisoformat(str(deadline_raw).replace("Z", "+00:00"))
                if dl.tzinfo is None:
                    dl = dl.replace(tzinfo=timezone.utc)
                if dl > now:
                    active_booking_ids.append(bk["id"])
            else:
                active_booking_ids.append(bk["id"])

    if active_booking_ids:
        taken_res = await asyncio.to_thread(
            lambda: supabase_admin.table("booking_seats")
                .select("seat_id")
                .in_("booking_id", active_booking_ids)
                .in_("seat_id", body.new_seat_ids)
                .execute()
        )
        taken = {row["seat_id"] for row in (taken_res.data or [])}
        if taken:
            raise HTTPException(status_code=409, detail=f"Seats {sorted(taken)} are not available")

    # Reject seats disabled by admin via showtime_seats.is_available
    ss_avail_res = await asyncio.to_thread(
        lambda: supabase_admin.table("showtime_seats")
            .select("seat_id, is_available")
            .eq("showtime_id", b["showtime_id"])
            .in_("seat_id", body.new_seat_ids)
            .execute()
    )
    admin_disabled = {
        row["seat_id"] for row in (ss_avail_res.data or [])
        if not row.get("is_available", True)
    }
    if admin_disabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Seats {sorted(admin_disabled)} are disabled for this showtime",
        )

    # Swap booking_seats
    await asyncio.to_thread(
        lambda: supabase_admin.table("booking_seats")
            .delete()
            .eq("booking_id", booking_id)
            .execute()
    )
    new_booking_seats = [
        {"booking_id": booking_id, "seat_id": sid, "showtime_id": b["showtime_id"]}
        for sid in body.new_seat_ids
    ]
    await asyncio.to_thread(
        lambda: supabase_admin.table("booking_seats").insert(new_booking_seats).execute()
    )

    # Swap tickets — preserve ticket_type and price_paid, regenerate QR slug
    tickets_res = await asyncio.to_thread(
        lambda: supabase_admin.table("tickets")
            .select("ticket_type, price_paid")
            .eq("booking_id", booking_id)
            .execute()
    )
    existing_tickets = tickets_res.data or []
    if existing_tickets:
        import secrets as _secrets
        await asyncio.to_thread(
            lambda: supabase_admin.table("tickets")
                .delete()
                .eq("booking_id", booking_id)
                .execute()
        )
        new_tickets = []
        for i, sid in enumerate(body.new_seat_ids):
            old_t = existing_tickets[i] if i < len(existing_tickets) else existing_tickets[-1]
            new_tickets.append({
                "booking_id": booking_id,
                "seat_id": sid,
                "ticket_type": old_t.get("ticket_type", "normal"),
                "price_paid": old_t.get("price_paid", 0),
                "qr_code_slug": _secrets.token_urlsafe(12),
            })
        await asyncio.to_thread(
            lambda: supabase_admin.table("tickets").insert(new_tickets).execute()
        )

    return {
        "booking_id": booking_id,
        "old_seat_ids": old_seat_ids,
        "new_seat_ids": body.new_seat_ids,
        "status": "confirmed",
        "price_difference": 0,
    }

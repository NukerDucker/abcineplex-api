"""
Booking API Routes
"""
from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional
from datetime import datetime

from app.schemas.booking import (
    ReserveSeatRequest,
    ReserveSeatResponse,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
    CancelBookingRequest,
    CancelBookingResponse,
    BookingDetail,
    AvailableSeat,
    ScreenInfo,
    ExpiryWorkerResponse,
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
    new_showtime_id: int,
    new_seat_ids: List[int],
    current_user: CurrentUser = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")


@router.post("/{booking_id}/change-seat")
async def change_seat(
    booking_id: str,
    new_seat_ids: List[int],
    current_user: CurrentUser = Depends(get_current_user),
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not yet implemented")

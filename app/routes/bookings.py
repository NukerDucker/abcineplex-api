"""
Booking API Routes
Handles all booking-related endpoints
"""
from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional
from uuid import UUID
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
    ScreenStatistics,
    ExpiryWorkerResponse
)
from app.crud.booking import CRUDBooking
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, get_admin_user, CurrentUser
import logging

logger = logging.getLogger(__name__)

_BOOKING_NOT_FOUND = "Booking not found"

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])
crud_booking = CRUDBooking(supabase_admin)


# ========== Seat Selection Endpoints ==========

@router.get("/screens", response_model=List[ScreenInfo])
async def get_screens():
    """Get all available screens"""
    try:
        screens = await crud_booking.get_all_screens()
        return screens
    except Exception as e:
        logger.error(f"Error getting screens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch screens: {str(e)}"
        )


@router.get("/screens/{screen_id}", response_model=ScreenInfo)
async def get_screen(screen_id: int):
    """Get screen details by ID"""
    try:
        screen = await crud_booking.get_screen_by_id(screen_id)
        if not screen:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Screen not found"
            )
        return screen
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting screen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch screen: {str(e)}"
        )


@router.get("/screens/{screen_id}/seats", response_model=List[AvailableSeat])
async def get_available_seats(screen_id: int):
    """
    Get all available seats for a specific screen.
    This is called when the user opens the seat selection page.
    """
    try:
        seats = await crud_booking.get_available_seats(screen_id)
        return seats
    except Exception as e:
        logger.error(f"Error getting available seats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch available seats: {str(e)}"
        )


@router.get("/screens/{screen_id}/seats/all")
async def get_all_seats(screen_id: int):
    """
    Get all seats for a screen (including reserved/sold).
    Useful for rendering the seat map with different states.
    """
    try:
        seats = await crud_booking.get_all_seats_for_screen(screen_id)
        return seats
    except Exception as e:
        logger.error(f"Error getting all seats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch seats: {str(e)}"
        )



# ========== Booking Flow Endpoints ==========

@router.post("", response_model=ReserveSeatResponse)
async def create_booking(
    request: ReserveSeatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Step 1: Reserve seats and create pending booking.
    Called when user proceeds to payment.
    Starts the 5-minute countdown timer.
    """
    try:
        result = await crud_booking.reserve_seats(request, user_id=current_user.user_id)

        if not result.get('success'):
            return ReserveSeatResponse(
                success=False,
                error=result.get('error', 'Failed to reserve seats'),
                unavailable_seats=result.get('unavailable_seats')
            )

        return ReserveSeatResponse(
            success=True,
            booking_id=result['booking_id'],
            payment_deadline=result['payment_deadline'],
            total_amount=request.price_per_seat * len(request.seat_ids)
        )

    except Exception as e:
        logger.error(f"Error reserving seats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reserve seats: {str(e)}"
        )


@router.post("/confirm-payment", response_model=ConfirmPaymentResponse)
async def confirm_payment(
    request: ConfirmPaymentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Step 2: Confirm payment and finalize booking.
    Called after payment gateway confirms successful payment.
    Changes seat status from 'reserved' to 'sold'.
    """
    try:
        # First check if booking exists
        booking = await crud_booking.get_booking_by_id(request.booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_BOOKING_NOT_FOUND
            )

        logger.info(f"Confirming payment for booking {request.booking_id}, current status: {booking.get('status')}")

        # If already confirmed, return the tickets (idempotent behavior)
        if booking['status'] == 'confirmed':
            logger.info(f"Booking {request.booking_id} already confirmed, returning existing tickets")
            tickets = await crud_booking.get_tickets_for_booking(request.booking_id)
            return ConfirmPaymentResponse(
                success=True,
                message="Payment already confirmed",
                booking_id=request.booking_id,
                tickets=tickets
            )

        if booking['status'] != 'pending':
            logger.warning(f"Cannot confirm payment - booking {request.booking_id} status is '{booking['status']}', expected 'pending' or 'confirmed'")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking cannot be confirmed. Current status: {booking['status']}"
            )

        # Confirm payment
        result = await crud_booking.confirm_payment(
            request.booking_id,
            request.payment_intent_id
        )

        if not result.get('success'):
            return ConfirmPaymentResponse(
                success=False,
                message=result.get('error', 'Failed to confirm payment')
            )

        # Get tickets
        tickets = await crud_booking.get_tickets_for_booking(request.booking_id)

        return ConfirmPaymentResponse(
            success=True,
            message="Payment confirmed successfully",
            booking_id=request.booking_id,
            tickets=tickets
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to confirm payment: {str(e)}"
        )


@router.post("/cancel", response_model=CancelBookingResponse)
async def cancel_booking_post(
    request: CancelBookingRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Cancel a pending booking (POST variant — kept for backward compatibility).
    Releases seats back to available status.
    """
    booking = await crud_booking.get_booking_by_id(request.booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_BOOKING_NOT_FOUND)

    if not current_user.is_admin and str(booking.get('user_id')) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

    try:
        result = await crud_booking.cancel_booking(request.booking_id)

        if not result.get('success'):
            return CancelBookingResponse(
                success=False,
                message=result.get('error', 'Failed to cancel booking')
            )

        return CancelBookingResponse(success=True, message="Booking cancelled successfully")

    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel booking: {str(e)}"
        )


@router.delete("/{booking_id}", response_model=CancelBookingResponse)
async def cancel_booking_delete(
    booking_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Cancel / delete a booking (DELETE variant per spec §5.6).
    Owner or admin only. No refund per theatre policy.
    """
    booking = await crud_booking.get_booking_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_BOOKING_NOT_FOUND)

    if not current_user.is_admin and str(booking.get('user_id')) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

    try:
        result = await crud_booking.cancel_booking(booking_id)

        if not result.get('success'):
            return CancelBookingResponse(
                success=False,
                message=result.get('error', 'Failed to cancel booking')
            )

        return CancelBookingResponse(
            success=True,
            message="Booking cancelled. No refund per theatre policy.",
        )

    except Exception as e:
        logger.error(f"Error cancelling booking {booking_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel booking: {str(e)}"
        )


# ========== Booking Information Endpoints ==========
# Note: GET /me is handled by GET /api/v1/users/me/bookings — removed duplicate

@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get detailed booking information including seats"""
    try:
        booking = await crud_booking.get_booking_details(booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_BOOKING_NOT_FOUND
            )

        # Basic Authorization: Owner or Admin
        if not current_user.is_admin and str(booking.user_id) != current_user.user_id:
            logger.warning(f"Unauthorized access attempt to booking {booking_id} by user {current_user.user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this booking"
            )

        return booking
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch booking: {str(e)}"
        )


@router.get("/{booking_id}/tickets")
async def get_booking_tickets(
    booking_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get all tickets for a booking (with QR codes)"""
    try:
        # Check ownership first
        booking = await crud_booking.get_booking_by_id(booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_BOOKING_NOT_FOUND
            )

        if not current_user.is_admin and str(booking.get('user_id')) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view these tickets"
            )

        tickets = await crud_booking.get_tickets_for_booking(booking_id)
        if not tickets:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tickets found for this booking"
            )
        return {"tickets": tickets}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch tickets: {str(e)}"
        )

# Note: User bookings are handled by GET /api/v1/users/me/bookings and GET /api/v1/users/{user_id}/bookings — removed duplicate


# ========== Statistics Endpoints ==========

@router.get("/stats/screens", response_model=List[ScreenStatistics])
async def get_screen_statistics():
    """
    Get occupancy statistics for all screens.
    Shows available, reserved, sold, and maintenance seats count.
    """
    try:
        stats = await crud_booking.get_screen_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error getting screen statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch screen statistics: {str(e)}"
        )


# ========== Worker Endpoint (Internal Use) ==========

@router.post("/internal/release-expired", response_model=ExpiryWorkerResponse)
async def release_expired_reservations(_: CurrentUser = Depends(get_admin_user)):
    """
    Internal endpoint to release expired reservations.
    Should be called by a cron job or worker every minute.
    Can also be called manually for testing.
    """
    try:
        result = await crud_booking.release_expired_reservations()

        from datetime import datetime
        return ExpiryWorkerResponse(
            released_count=result.get('released_count', 0),
            booking_ids=result.get('booking_ids'),
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"Error releasing expired reservations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release expired reservations: {str(e)}"
        )


# ========== Self-Service Endpoints ==========

@router.post("/{booking_id}/change-showtime")
async def change_showtime(
    booking_id: UUID,
    new_showtime_id: int,
    new_seat_ids: List[int],
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Self-service showtime change. No refund; difference charged if new showtime is more expensive.
    User must make the change at least 30 minutes before original showtime starts.
    """
    try:
        # TODO: Implement full business logic
        # - Validate booking exists and belongs to user
        # - Validate new showtime exists and is >= 30 min away
        # - Validate seats are available
        # - Calculate price difference
        # - Update booking status to "changed"
        # - Update booking_seats with new seats
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Endpoint not yet implemented"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing showtime: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change showtime: {str(e)}"
        )


@router.post("/{booking_id}/change-seat")
async def change_seat(
    booking_id: UUID,
    new_seat_ids: List[int],
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Self-service seat change within the same showtime.
    User can change seats anytime before showtime starts.
    """
    try:
        # TODO: Implement full business logic
        # - Validate booking exists and belongs to user
        # - Validate showtime hasn't started yet
        # - Validate seats are available
        # - Update booking_seats with new seats
        # - Return updated booking
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Endpoint not yet implemented"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing seat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to change seat: {str(e)}"
        )

# ========== Admin Endpoints ==========
# Moved to /api/v1/admin/ in app/routes/admin.py

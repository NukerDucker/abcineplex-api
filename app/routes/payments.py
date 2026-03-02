"""
Payment (Mock) API Routes — §5.7
Simulates a payment gateway without real financial integration.
State is stored in-memory (intentional — this is a mock system).
"""
from fastapi import APIRouter, HTTPException, status, Depends
from uuid import uuid4
from datetime import datetime
import asyncio

from app.crud.booking import CRUDBooking
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, CurrentUser
from app.schemas.payment import (
    PaymentInitiateRequest,
    PaymentInitiateResponse,
    PaymentConfirmRequest,
    PaymentConfirmResponse,
    PaymentStatusResponse,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])
crud_booking = CRUDBooking(supabase_admin)

# ── In-memory mock payment store ──────────────────────────────────────────────
# Dict[payment_id -> payment record]
_payments: dict[str, dict] = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/initiate", response_model=PaymentInitiateResponse, status_code=status.HTTP_200_OK)
async def initiate_payment(
    request: PaymentInitiateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Initiate a mock payment for a booking.
    Returns a payment_id to be confirmed in the next step.
    """
    booking = await crud_booking.get_booking_by_id(str(request.booking_id))
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    if not current_user.is_admin and str(booking.get("user_id")) != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")

    if booking.get("booking_status") not in ("pending",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Booking is not in a payable state. Status: {booking.get('booking_status')}",
        )

    payment_id = str(uuid4())
    _payments[payment_id] = {
        "payment_id": payment_id,
        "booking_id": request.booking_id,
        "amount": float(booking.get("total_amount", 0)),
        "payment_method": request.payment_method,
        "mock_should_succeed": request.mock_should_succeed,
        "status": "pending",
        "paid_at": None,
    }

    logger.info(f"Payment {payment_id} initiated for booking {request.booking_id}")
    return PaymentInitiateResponse(
        payment_id=payment_id,
        status="pending",
        amount=_payments[payment_id]["amount"],
        payment_method=request.payment_method,
    )


@router.post("/{payment_id}/confirm", response_model=PaymentConfirmResponse)
async def confirm_payment(
    payment_id: str,
    request: PaymentConfirmRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Confirm (or decline) a mock payment.
    On success: finalises booking, marks seats sold, generates QR tickets.
    On failure: leaves booking as pending so the user can retry.
    """
    record = _payments.get(payment_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    booking_id: str = str(record["booking_id"])

    # Resolve success: both the request flag AND the stored flag must agree
    is_success = request.mock_result and record.get("mock_should_succeed", True)

    if not is_success:
        record["status"] = "failed"
        logger.info(f"Payment {payment_id} declined (mock failure)")
        return PaymentConfirmResponse(
            payment_id=payment_id,
            status="failed",
            booking_id=booking_id,
            booking_status="pending",
            message="Payment declined (mock failure)",
        )

    # Delegate to the existing booking confirmation logic
    try:
        result = await crud_booking.confirm_payment(
            str(booking_id),
            payment_intent_id=record['payment_method'],
        )
    except Exception as e:
        logger.error(f"confirm_payment RPC failed for payment {payment_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment gateway error — please try again",
        )

    if not result.get("success"):
        record["status"] = "failed"
        return PaymentConfirmResponse(
            payment_id=payment_id,
            status="failed",
            booking_id=booking_id,
            booking_status="pending",
            message=result.get("error", "Payment confirmation failed"),
        )

    record["status"] = "success"
    record["paid_at"] = datetime.now().isoformat()

    # Estimate points earned: 1 pt per 10 baht (rounded)
    points_earned = max(1, int(record["amount"] / 10))

    # EP08-UC001 & EP08-UC003: Persist points + increment attendance streak
    try:
        user_res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select("loyalty_points, attendance_streak")
                .eq("id", current_user.user_id)
                .maybe_single()
                .execute()
        )
        if user_res.data:
            current_pts = (user_res.data.get("loyalty_points") or 0)
            # EP-25: Deduct redeemed points, then add earned points
            redeemed = min(request.points_redeemed, current_pts)
            new_pts = current_pts - redeemed + points_earned
            new_streak = (user_res.data.get("attendance_streak") or 0) + 1
            await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .update({"loyalty_points": new_pts, "attendance_streak": new_streak})
                    .eq("id", current_user.user_id)
                    .execute()
            )
    except Exception as e:
        logger.warning(f"Could not update loyalty points/streak: {e}")

    logger.info(f"Payment {payment_id} confirmed for booking {booking_id}")
    return PaymentConfirmResponse(
        payment_id=payment_id,
        status="success",
        booking_id=booking_id,
        booking_status="confirmed",
        points_earned=points_earned,
    )


@router.get("/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment(
    payment_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the current status of a mock payment."""
    record = _payments.get(payment_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return PaymentStatusResponse(
        payment_id=record["payment_id"],
        booking_id=record["booking_id"],
        status=record["status"],
        amount=record["amount"],
        payment_method=record["payment_method"],
        paid_at=datetime.fromisoformat(record["paid_at"]) if record.get("paid_at") else None,
    )

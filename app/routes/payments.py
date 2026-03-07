"""
Payment (Mock) API Routes — §5.7
Simulates a payment gateway without real financial integration.
State is persisted in the payments DB table for durability.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from typing import Optional
import asyncio

from app.crud.booking import CRUDBooking
from app.crud.movie import CRUDMovie
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, get_optional_user, CurrentUser
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
crud_movie = CRUDMovie(supabase_admin)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _fetch_payment(payment_id: str) -> Optional[dict]:
    """Fetch a payment row from the DB."""
    res = await asyncio.to_thread(
        lambda: supabase_admin.table("payments")
            .select("*")
            .eq("id", payment_id)
            .maybe_single()
            .execute()
    )
    return res.data


async def _recalculate_consensus(booking_id: str) -> None:
    """Best-effort consensus score recalc after a confirmed booking."""
    booking_detail = await crud_booking.get_booking_by_id(booking_id)
    if not booking_detail:
        return
    showtime_id = booking_detail.get("showtime_id")
    if not showtime_id:
        return
    st_res = await asyncio.to_thread(
        lambda: supabase_admin.table("showtimes")
            .select("movie_id")
            .eq("id", showtime_id)
            .maybe_single()
            .execute()
    )
    if st_res.data and st_res.data.get("movie_id"):
        await crud_movie.recalculate_consensus_score(st_res.data["movie_id"])


async def _apply_loyalty(
    booking_id: str,
    amount: float,
    points_redeemed: int,
    user: CurrentUser,
) -> int:
    """Award points + streak for an authenticated user. Returns points earned."""
    booking_res = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("num_tickets")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    num_tickets = (booking_res.data or {}).get("num_tickets") or 1
    points_earned = 50 * num_tickets
    points_discount = min(points_redeemed, int(amount))
    final_amount = max(0, amount - points_discount)
    await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .update({"points_redeemed": points_redeemed, "final_amount_paid": final_amount})
            .eq("id", booking_id)
            .execute()
    )
    user_res = await asyncio.to_thread(
        lambda: supabase_admin.table("users")
            .select("loyalty_points, attendance_streak")
            .eq("id", user.user_id)
            .maybe_single()
            .execute()
    )
    if user_res.data:
        current_pts = user_res.data.get("loyalty_points") or 0
        new_pts = current_pts - min(points_redeemed, current_pts) + points_earned
        new_streak = (user_res.data.get("attendance_streak") or 0) + 1
        await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .update({"loyalty_points": new_pts, "attendance_streak": new_streak})
                .eq("id", user.user_id)
                .execute()
        )
    return points_earned


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/initiate", response_model=PaymentInitiateResponse, status_code=status.HTTP_200_OK)
async def initiate_payment(
    request: PaymentInitiateRequest,
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """
    Initiate a mock payment for a booking or snack order.
    Exactly one of booking_id or order_id must be set.
    Supports authenticated users (Bearer token) and guest users (guest_token field).
    """
    # ── Booking payment path ────────────────────────────────────────────────
    if request.booking_id:
        booking = await crud_booking.get_booking_by_id(str(request.booking_id))
        if not booking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

        is_guest = bool(request.guest_token)
        if is_guest:
            gs_res = await asyncio.to_thread(
                lambda: supabase_admin.table("guest_sessions")
                    .select("booking_id")
                    .eq("token", request.guest_token)
                    .eq("booking_id", str(request.booking_id))
                    .maybe_single()
                    .execute()
            )
            if not gs_res.data:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired guest token")
        elif current_user:
            if not current_user.is_admin and str(booking.get("user_id")) != current_user.user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your booking")
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

        if booking.get("booking_status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking is not in a payable state. Status: {booking.get('booking_status')}",
            )

        amount = float(booking.get("total_amount", 0))
        insert_data = {
            "booking_id": str(request.booking_id),
            "order_id":   None,
            "amount":     amount,
            "payment_method": request.payment_method,
            "status":     "pending",
            "mock_should_succeed": request.mock_should_succeed,
        }

    # ── Snack order payment path ────────────────────────────────────────────
    else:
        if not current_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

        order_res = await asyncio.to_thread(
            lambda: supabase_admin.table("orders")
                .select("*")
                .eq("id", str(request.order_id))
                .maybe_single()
                .execute()
        )
        if not order_res.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        order = order_res.data

        if not current_user.is_admin and str(order.get("user_id")) != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your order")

        if order.get("order_status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order is not in a payable state. Status: {order.get('order_status')}",
            )

        amount = float(order.get("total_amount", 0))
        insert_data = {
            "booking_id": None,
            "order_id":   str(request.order_id),
            "amount":     amount,
            "payment_method": request.payment_method,
            "status":     "pending",
            "mock_should_succeed": request.mock_should_succeed,
        }

    # ── Persist to DB ───────────────────────────────────────────────────────
    payment_row = await asyncio.to_thread(
        lambda: supabase_admin.table("payments").insert(insert_data).execute()
    )
    if not payment_row.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create payment record")

    payment_id = payment_row.data[0]["id"]
    logger.info(f"Payment {payment_id} initiated for {'booking' if request.booking_id else 'order'} {request.booking_id or request.order_id}")

    return PaymentInitiateResponse(
        payment_id=payment_id,
        status="pending",
        amount=amount,
        payment_method=request.payment_method,
    )


@router.post("/{payment_id}/confirm", response_model=PaymentConfirmResponse)
async def confirm_payment(
    payment_id: str,
    request: PaymentConfirmRequest,
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """
    Confirm (or decline) a mock payment.
    On success: finalises booking or order, awards points (tickets only).
    On failure: leaves booking/order as pending so the user can retry via a new initiate call.
    """
    record = await _fetch_payment(payment_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    booking_id: Optional[str] = record.get("booking_id")
    order_id:   Optional[str] = record.get("order_id")
    is_success = request.mock_result and record.get("mock_should_succeed", True)

    if not is_success:
        await asyncio.to_thread(
            lambda: supabase_admin.table("payments")
                .update({"status": "failed", "mock_result": request.mock_result})
                .eq("id", payment_id)
                .execute()
        )
        logger.info(f"Payment {payment_id} declined (mock failure)")
        return PaymentConfirmResponse(
            payment_id=payment_id,
            status="failed",
            booking_id=booking_id,
            order_id=order_id,
            booking_status="pending" if booking_id else None,
            order_status="pending" if order_id else None,
            message="Payment declined (mock failure)",
        )

    # ── Success path ────────────────────────────────────────────────────────
    points_earned = 0

    if booking_id:
        # Confirm ticket booking via existing RPC
        try:
            result = await crud_booking.confirm_payment(
                str(booking_id),
                payment_intent_id=record.get("payment_method"),
            )
        except Exception as e:
            logger.error(f"confirm_payment RPC failed for payment {payment_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Payment gateway error — please try again",
            )

        if not result.get("success"):
            await asyncio.to_thread(
                lambda: supabase_admin.table("payments")
                    .update({"status": "failed", "mock_result": request.mock_result})
                    .eq("id", payment_id)
                    .execute()
            )
            return PaymentConfirmResponse(
                payment_id=payment_id,
                status="failed",
                booking_id=booking_id,
                booking_status="pending",
                message=result.get("error", "Payment confirmation failed"),
            )

        # Award loyalty points for ticket purchase
        try:
            if current_user:
                points_earned = await _apply_loyalty(
                    booking_id, record["amount"], request.points_redeemed, current_user
                )
            else:
                await asyncio.to_thread(
                    lambda: supabase_admin.table("bookings")
                        .update({"points_redeemed": 0, "final_amount_paid": record["amount"]})
                        .eq("id", booking_id)
                        .execute()
                )
        except Exception as e:
            logger.warning(f"Could not update loyalty points: {e}")

        try:
            await _recalculate_consensus(booking_id)
        except Exception as e:
            logger.warning(f"Could not recalculate consensus score: {e}")

        await asyncio.to_thread(
            lambda: supabase_admin.table("payments")
                .update({"status": "success", "mock_result": request.mock_result})
                .eq("id", payment_id)
                .execute()
        )
        logger.info(f"Payment {payment_id} confirmed for booking {booking_id}")
        return PaymentConfirmResponse(
            payment_id=payment_id,
            status="success",
            booking_id=booking_id,
            booking_status="confirmed",
            points_earned=points_earned,
        )

    else:
        # Confirm snack order
        await asyncio.to_thread(
            lambda: supabase_admin.table("orders")
                .update({"order_status": "confirmed"})
                .eq("id", str(order_id))
                .execute()
        )
        await asyncio.to_thread(
            lambda: supabase_admin.table("payments")
                .update({"status": "success", "mock_result": request.mock_result})
                .eq("id", payment_id)
                .execute()
        )
        logger.info(f"Payment {payment_id} confirmed for order {order_id}")
        return PaymentConfirmResponse(
            payment_id=payment_id,
            status="success",
            order_id=order_id,
            order_status="confirmed",
            points_earned=0,
            message="Snack order confirmed",
        )


@router.get("/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment(
    payment_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the current status of a payment (reads from DB)."""
    record = await _fetch_payment(payment_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return PaymentStatusResponse(
        payment_id=record["id"],
        booking_id=record.get("booking_id"),
        order_id=record.get("order_id"),
        status=record["status"],
        amount=float(record["amount"]),
        payment_method=record["payment_method"],
        paid_at=datetime.fromisoformat(record["paid_at"]) if record.get("paid_at") else None,
    )

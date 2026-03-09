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


async def _log_transaction(user_id: str, points_delta: int, reason: str, reference_id: Optional[str] = None) -> None:
    """Insert a row into membership_transactions. Best-effort — never raises."""
    try:
        row: dict = {"user_id": user_id, "points_delta": points_delta, "reason": reason}
        if reference_id is not None:
            row["reference_id"] = reference_id
        await asyncio.to_thread(
            lambda: supabase_admin.table("membership_transactions").insert(row).execute()
        )
    except Exception as e:
        logger.warning(f"membership_transactions insert failed: {e}")


async def _apply_loyalty(
    booking_id: str,
    amount: float,
    points_redeemed: int,
    user: CurrentUser,
) -> int:
    """
    Award points + update streak for an authenticated user. Returns points earned.

    Rules enforced here:
    - Points redemption validated against current balance (raises 400 if insufficient)
    - Streak resets to 1 if gap since last confirmed booking > 7 days
    - Milestone bonuses at streak 3 (+50), 5 (+100), 10 (+200) awarded only once
    - Referral bonus (+50 each) awarded on user's first confirmed booking
    - All point changes logged to membership_transactions
    """
    from datetime import timezone, timedelta
    from fastapi import HTTPException

    booking_res = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("num_tickets")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    num_tickets = (booking_res.data or {}).get("num_tickets") or 1
    points_earned = 50 * num_tickets

    user_res = await asyncio.to_thread(
        lambda: supabase_admin.table("users")
            .select("loyalty_points, attendance_streak")
            .eq("id", user.user_id)
            .maybe_single()
            .execute()
    )
    user_data = user_res.data or {}
    current_pts = user_data.get("loyalty_points") or 0

    # Validate points redemption before doing anything
    if points_redeemed > current_pts:
        raise HTTPException(status_code=400, detail="Insufficient loyalty points balance")

    points_discount = min(points_redeemed, int(amount))
    final_amount = max(0, amount - points_discount)

    await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .update({"points_redeemed": points_redeemed, "final_amount_paid": final_amount})
            .eq("id", booking_id)
            .execute()
    )

    # ── Streak calculation ─────────────────────────────────────────────────────
    # Fetch the most recent prior ticket_purchase transaction to determine gap
    last_tx_res = await asyncio.to_thread(
        lambda: supabase_admin.table("membership_transactions")
            .select("created_at")
            .eq("user_id", user.user_id)
            .eq("reason", "ticket_purchase")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
    )
    last_tx_rows = last_tx_res.data or []
    is_first_booking = len(last_tx_rows) == 0

    now = datetime.now(timezone.utc)
    if last_tx_rows:
        raw_ts = last_tx_rows[0].get("created_at", "")
        last_dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        gap_days = (now - last_dt).days
        streak_resets = gap_days > 7
    else:
        streak_resets = False

    current_streak = user_data.get("attendance_streak") or 0
    new_streak = 1 if streak_resets else current_streak + 1

    # ── Update user balance + streak ───────────────────────────────────────────
    new_pts = current_pts - points_discount + points_earned
    await asyncio.to_thread(
        lambda: supabase_admin.table("users")
            .update({"loyalty_points": new_pts, "attendance_streak": new_streak})
            .eq("id", user.user_id)
            .execute()
    )

    # ── Log transactions ───────────────────────────────────────────────────────
    await _log_transaction(user.user_id, points_earned, "ticket_purchase", booking_id)
    if points_redeemed > 0:
        await _log_transaction(user.user_id, -points_redeemed, "points_redemption", booking_id)

    # ── Streak milestone bonuses (only once per milestone) ─────────────────────
    MILESTONES = {3: 50, 5: 100, 10: 200}
    if new_streak in MILESTONES:
        milestone_reason = f"streak_milestone_{new_streak}"
        already_res = await asyncio.to_thread(
            lambda: supabase_admin.table("membership_transactions")
                .select("id", count="exact")
                .eq("user_id", user.user_id)
                .eq("reason", milestone_reason)
                .execute()
        )
        if (already_res.count or 0) == 0:
            bonus = MILESTONES[new_streak]
            await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .update({"loyalty_points": new_pts + bonus})
                    .eq("id", user.user_id)
                    .execute()
            )
            await _log_transaction(user.user_id, bonus, milestone_reason, booking_id)
            new_pts += bonus

    # ── Referral bonus on first confirmed booking ──────────────────────────────
    if is_first_booking:
        ref_row_res = await asyncio.to_thread(
            lambda: supabase_admin.table("referrals")
                .select("id, referrer_id")
                .eq("referred_id", user.user_id)
                .eq("points_awarded", False)
                .maybe_single()
                .execute()
        )
        if ref_row_res.data:
            referral_id = ref_row_res.data["id"]
            referrer_id = ref_row_res.data["referrer_id"]

            referrer_res = await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .select("loyalty_points")
                    .eq("id", referrer_id)
                    .maybe_single()
                    .execute()
            )
            referrer_pts = (referrer_res.data or {}).get("loyalty_points") or 0
            await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .update({"loyalty_points": referrer_pts + 50})
                    .eq("id", referrer_id)
                    .execute()
            )
            await _log_transaction(referrer_id, 50, "referral_bonus", user.user_id)

            await asyncio.to_thread(
                lambda: supabase_admin.table("referrals")
                    .update({"points_awarded": True})
                    .eq("id", referral_id)
                    .execute()
            )
            logger.info(f"Referral bonus: referrer {referrer_id} +50 pts (referred user {user.user_id})")

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
        # Confirm snack order — apply points redemption if requested
        snack_points_redeemed = request.points_redeemed if current_user else 0
        snack_amount = float(record.get("amount", 0))

        if current_user and snack_points_redeemed > 0:
            user_pts_res = await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .select("loyalty_points")
                    .eq("id", current_user.user_id)
                    .maybe_single()
                    .execute()
            )
            snack_current_pts = (user_pts_res.data or {}).get("loyalty_points") or 0
            if snack_points_redeemed > snack_current_pts:
                raise HTTPException(status_code=400, detail="Insufficient loyalty points balance")
            points_discount = min(snack_points_redeemed, int(snack_amount))
            new_snack_pts = snack_current_pts - points_discount
            await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .update({"loyalty_points": new_snack_pts})
                    .eq("id", current_user.user_id)
                    .execute()
            )
            await _log_transaction(current_user.user_id, -points_discount, "points_redemption_snack", str(order_id))

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

        # Award 1 loyalty point per 10 baht spent on snacks
        snack_points_earned = 0
        if current_user:
            snack_points_earned = int(snack_amount / 10)
            if snack_points_earned > 0:
                pts_res = await asyncio.to_thread(
                    lambda: supabase_admin.table("users")
                        .select("loyalty_points")
                        .eq("id", current_user.user_id)
                        .maybe_single()
                        .execute()
                )
                current_pts = (pts_res.data or {}).get("loyalty_points", 0) or 0
                await asyncio.to_thread(
                    lambda: supabase_admin.table("users")
                        .update({"loyalty_points": current_pts + snack_points_earned})
                        .eq("id", current_user.user_id)
                        .execute()
                )
                await _log_transaction(current_user.user_id, snack_points_earned, "snack_purchase", str(order_id))

        logger.info(f"Payment {payment_id} confirmed for order {order_id}")
        return PaymentConfirmResponse(
            payment_id=payment_id,
            status="success",
            order_id=order_id,
            order_status="confirmed",
            points_earned=snack_points_earned,
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

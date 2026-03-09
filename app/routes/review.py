from fastapi import APIRouter, Depends, HTTPException, Query
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from app.schemas.review import (
    ReviewCreate,
    ReviewUpdate,
    ReviewListResponse,
    ReviewResponse,
    ReviewLikeResponse,
    ReviewWithMovie,
    ReviewWithMovieListResponse,
)
from app.crud.review import CRUDReview
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import NotFoundException, AppException

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])
# Spec-path aliases mounted at the movie/booking-nested URLs
spec_router = APIRouter(tags=["reviews"])
crud_review = CRUDReview(supabase_admin)


# -------- GET LATEST REVIEWS (community feed) --------
@router.get("/latest", response_model=ReviewWithMovieListResponse)
async def read_latest_reviews(
    limit: int = Query(20, ge=1, le=100),
):
    """Get latest reviews across all movies for community feed"""
    return await crud_review.get_latest(limit=limit, user_id=None)


# -------- GET MY REVIEWS --------
@router.get("/me", response_model=ReviewWithMovieListResponse)
async def read_my_reviews(
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get all reviews written by the current user"""
    return await crud_review.get_by_user(user_id=current_user.user_id)


# -------- GET REVIEWS (WITH TOTAL COUNT) --------
@router.get("/movie/{movie_id}", response_model=ReviewListResponse)
async def read_reviews_by_movie(
    movie_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """Get all reviews for a specific movie"""
    return await crud_review.get_by_movie(movie_id, skip, limit)


async def _resolve_booking_context(booking_id: str, user_id: str) -> dict:
    """Validate booking ownership and return showtime context fields to merge into review_data."""
    booking = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("user_id, showtime_id, booking_status")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    if str(booking.data.get("user_id")) != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to review this booking")
    if booking.data.get("booking_status") != "confirmed":
        raise HTTPException(status_code=400, detail="Can only review confirmed bookings")

    extras: dict = {"booking_id": booking_id}
    showtime_id = booking.data.get("showtime_id")
    if not showtime_id:
        return extras

    st = await asyncio.to_thread(
        lambda: supabase_admin.table("showtimes")
            .select("start_time, theatre_id")
            .eq("id", showtime_id)
            .maybe_single()
            .execute()
    )
    if not st.data:
        return extras

    start_time_raw = st.data.get("start_time")
    if start_time_raw:
        start_dt = datetime.fromisoformat(str(start_time_raw).replace("Z", "+00:00"))
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if start_dt > datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Showtime has not started yet")

    # showtime_id is NOT stored — movie_reviews has no showtime_id column (derive via bookings.showtime_id)
    return extras


async def _award_review_points(user_id: str, review_id: Optional[int] = None) -> None:
    """Award 20 loyalty points, set points_awarded flag, and log the transaction. Best-effort — never raises."""
    try:
        user_res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select("loyalty_points")
                .eq("id", user_id)
                .maybe_single()
                .execute()
        )
        if user_res.data:
            new_pts = (user_res.data.get("loyalty_points") or 0) + 20
            await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .update({"loyalty_points": new_pts})
                    .eq("id", user_id)
                    .execute()
            )
            # Log to membership_transactions
            tx_row: dict = {"user_id": user_id, "points_delta": 20, "reason": "review_points"}
            if review_id:
                tx_row["reference_id"] = str(review_id)
            await asyncio.to_thread(
                lambda: supabase_admin.table("membership_transactions").insert(tx_row).execute()
            )
        if review_id:
            await asyncio.to_thread(
                lambda: supabase_admin.table("movie_reviews")
                    .update({"points_awarded": True})
                    .eq("id", review_id)
                    .execute()
            )
    except Exception:
        pass


# -------- CREATE --------
@router.post("", response_model=ReviewResponse)
async def create_review(
    review_in: ReviewCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new review for a movie. Optionally linked to a booking."""
    review_data = review_in.model_dump(exclude={"booking_id"})
    review_data["user_id"] = current_user.user_id

    if review_in.booking_id:
        extras = await _resolve_booking_context(review_in.booking_id, current_user.user_id)
        review_data.update(extras)

    try:
        result = await crud_review.create(review_data)
        review_id = result.id if hasattr(result, "id") else None
        await _award_review_points(current_user.user_id, review_id)
        return result
    except ValueError as e:
        err = str(e)
        if err == "DUPLICATE_REVIEW":
            raise HTTPException(status_code=409, detail="You have already reviewed this movie.")
        if "idx_reviews_one_per_booking" in err or "23505" in err:
            raise HTTPException(status_code=409, detail="You have already reviewed this booking.")
        raise HTTPException(status_code=400, detail=err)


# -------- REVIEW STATUS --------
@router.get("/booking/{booking_id}/status")
async def get_review_status(
    booking_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Check if current user can review a booking. Used to show/hide Write a Review button."""
    booking = await asyncio.to_thread(
        lambda: supabase_admin.table("bookings")
            .select("user_id, showtime_id, booking_status")
            .eq("id", booking_id)
            .maybe_single()
            .execute()
    )
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    if str(booking.data.get("user_id")) != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    showtime_id = booking.data.get("showtime_id")
    showtime_passed = False
    movie_id = None

    if showtime_id:
        st = await asyncio.to_thread(
            lambda: supabase_admin.table("showtimes")
                .select("start_time, movie_id")
                .eq("id", showtime_id)
                .maybe_single()
                .execute()
        )
        if st.data:
            movie_id = st.data.get("movie_id")
            start_raw = st.data.get("start_time")
            if start_raw:
                start_dt = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                showtime_passed = start_dt < datetime.now(timezone.utc)

    already_reviewed = False
    if showtime_passed:
        rev = await asyncio.to_thread(
            lambda: supabase_admin.table("movie_reviews")
                .select("id", count="exact")
                .eq("booking_id", booking_id)
                .execute()
        )
        already_reviewed = (rev.count or 0) > 0

    return {
        "booking_id": booking_id,
        "can_review": showtime_passed and not already_reviewed and booking.data.get("booking_status") == "confirmed",
        "already_reviewed": already_reviewed,
        "showtime_has_passed": showtime_passed,
        "movie_id": movie_id,
        "showtime_id": showtime_id,
    }


# -------- UPDATE --------
@router.patch("/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: int,
    review_in: ReviewUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update an existing review (only if owner)"""
    updated = await crud_review.update(
        review_id,
        review_in.model_dump(exclude_unset=True),
        current_user.user_id
    )
    if not updated:
        raise NotFoundException("Review", str(review_id))
    return updated


# -------- DELETE --------
@router.delete("/{review_id}")
async def delete_review(
    review_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a review (only if owner)"""
    success = await crud_review.delete(review_id, current_user.user_id)
    if not success:
        raise NotFoundException("Review", str(review_id))
    return {"status": "success", "message": "Review deleted"}


# -------- LIKE --------
@router.post("/{review_id}/likes", response_model=ReviewLikeResponse)
async def add_review_like(
    review_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Like a review"""
    try:
        return await crud_review.add_like(review_id, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{review_id}/likes")
async def remove_review_like(
    review_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Unlike a review"""
    success = await crud_review.remove_like(review_id, current_user.user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Like not found")
    return {"status": "success", "message": "Like removed"}


# ── Spec-path aliases ─────────────────────────────────────────────────────────
# These expose the same logic at the spec-required nested paths so both the
# original /api/v1/reviews/... paths and the spec paths work simultaneously.

class _MovieReviewCreate(ReviewCreate):
    """Same as ReviewCreate but movie_id is optional — overridden by path param."""
    movie_id: Optional[int] = None


@spec_router.post("/api/v1/movies/{movie_id}/reviews", response_model=ReviewResponse)
async def create_review_spec(
    movie_id: int,
    review_in: _MovieReviewCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Spec-path alias: POST /movies/:id/reviews"""
    review_data = review_in.model_dump(exclude={"booking_id"})
    review_data["user_id"] = current_user.user_id
    review_data["movie_id"] = movie_id  # path param takes precedence

    if review_in.booking_id:
        extras = await _resolve_booking_context(review_in.booking_id, current_user.user_id)
        review_data.update(extras)

    try:
        result = await crud_review.create(review_data)
        spec_review_id = result.id if hasattr(result, "id") else None
        await _award_review_points(current_user.user_id, spec_review_id)
        return result
    except ValueError as e:
        err = str(e)
        if err == "DUPLICATE_REVIEW":
            raise HTTPException(status_code=409, detail="You have already reviewed this movie.")
        if "idx_reviews_one_per_booking" in err or "23505" in err:
            raise HTTPException(status_code=409, detail="You have already reviewed this booking.")
        raise HTTPException(status_code=400, detail=err)


@spec_router.get("/api/v1/movies/{movie_id}/reviews", response_model=ReviewListResponse)
async def get_movie_reviews_spec(
    movie_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    """Spec-path alias: GET /movies/:id/reviews"""
    skip = (page - 1) * limit
    return await crud_review.get_by_movie(movie_id, skip, limit)


@spec_router.get("/api/v1/bookings/{booking_id}/review-status")
async def get_booking_review_status_spec(
    booking_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Spec-path alias: GET /bookings/:id/review-status"""
    return await get_review_status(booking_id, current_user)
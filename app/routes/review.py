from fastapi import APIRouter, Depends, HTTPException, Query
import asyncio
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


# -------- CREATE --------
@router.post("", response_model=ReviewResponse)
async def create_review(
    review_in: ReviewCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new review for a movie"""
    try:
        # Add user info to review data
        review_data = review_in.model_dump()
        review_data["user_id"] = current_user.user_id
        review_data["username"] = current_user.user_name or current_user.email.split("@")[0]

        result = await crud_review.create(review_data, user_id=current_user.user_id)

        # Award 20 loyalty points for submitting a review (EP08-UC002)
        try:
            user_res = await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .select("loyalty_points")
                    .eq("id", current_user.user_id)
                    .maybe_single()
                    .execute()
            )
            if user_res.data:
                new_pts = (user_res.data.get("loyalty_points") or 0) + 20
                await asyncio.to_thread(
                    lambda: supabase_admin.table("users")
                        .update({"loyalty_points": new_pts})
                        .eq("id", current_user.user_id)
                        .execute()
                )
        except Exception:
            pass  # Points award is best-effort; don't fail the review creation

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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

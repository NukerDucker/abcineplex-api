from supabase import Client
from typing import List, Optional
import asyncio

# Join users so callers get user_name without a separate query.
# The username column was dropped from movie_reviews — users.user_name is
# the single source of truth.
_REVIEW_SELECT = "*, users!inner(user_name)"
_REVIEW_WITH_MOVIE_SELECT = "*, users!inner(user_name), movies!inner(id, title, poster_url, release_date)"


def _build_showtime_label(start_time, theatre_name: str) -> str:
    """Format: 'Sat 1 Mar 2026, 19:00 — Hall A'"""
    from datetime import datetime as _dt
    if not start_time:
        return ""
    dt = _dt.fromisoformat(str(start_time).replace("Z", "+00:00")) if isinstance(start_time, str) else start_time
    return dt.strftime("%-d %b %Y, %H:%M") + f" — {theatre_name}"


def _flatten_user(review: dict) -> dict:
    """
    Pull users.user_name up to the top level as 'username' so downstream
    schemas and response models continue to receive the same field name.
    """
    user_data = review.pop("users", None) or {}
    review["username"] = user_data.get("user_name")
    return review


class CRUDReview:
    __slots__ = ("client",)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def _enrich_with_movie(self, review: dict) -> dict:
        """Pull movies sub-object up into a 'movie' key."""
        movies_data = review.pop("movies", None)
        review["movie"] = movies_data if isinstance(movies_data, dict) else None
        return review

    async def get_by_movie(self, movie_id: int, skip: int = 0, limit: int = 20) -> dict:
        """Get reviews for a movie with total count."""
        def fetch_data():
            count_res = (
                self.client.table("movie_reviews")
                    .select("id", count="exact")
                    .eq("movie_id", movie_id)
                    .execute()
            )
            reviews_res = (
                self.client.table("movie_reviews")
                    .select(_REVIEW_SELECT)
                    .eq("movie_id", movie_id)
                    .order("created_at", desc=True)
                    .range(skip, skip + limit - 1)
                    .execute()
            )
            return count_res.count or 0, reviews_res.data or []

        total, items = await asyncio.to_thread(fetch_data)
        items = [_flatten_user(dict(r)) for r in items]
        return {"total": total, "items": items}

    async def get_latest(self, limit: int = 20, user_id: Optional[str] = None) -> dict:
        """Get latest reviews across all movies, enriched with movie info."""
        def fetch():
            res = (
                self.client.table("movie_reviews")
                    .select(_REVIEW_WITH_MOVIE_SELECT)
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
            )
            rows = res.data or []

            if user_id and rows:
                liked_res = (
                    self.client.table("review_likes")
                        .select("review_id")
                        .eq("user_id", user_id)
                        .in_("review_id", [r["id"] for r in rows])
                        .execute()
                )
                liked_set = {l["review_id"] for l in (liked_res.data or [])}
            else:
                liked_set = set()

            result = []
            for r in rows:
                r = _flatten_user(dict(r))
                r = self._enrich_with_movie(r)
                r["user_liked"] = r["id"] in liked_set
                result.append(r)
            return result

        items = await asyncio.to_thread(fetch)
        return {"total": len(items), "items": items}

    async def get_by_user(self, user_id: str, limit: int = 50) -> dict:
        """Get all reviews written by a specific user, enriched with movie info."""
        def fetch():
            res = (
                self.client.table("movie_reviews")
                    .select(_REVIEW_WITH_MOVIE_SELECT)
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute()
            )
            rows = res.data or []
            result = []
            for r in rows:
                r = _flatten_user(dict(r))
                r = self._enrich_with_movie(r)
                result.append(r)
            return result

        items = await asyncio.to_thread(fetch)
        return {"total": len(items), "items": items}

    async def create(self, review_in: dict, user_id: str) -> dict:
        """Create new review — one per user per movie (enforced by DB unique constraint)."""
        def validate_and_create():
            try:
                insert_res = self.client.table("movie_reviews").insert(review_in).execute()
            except Exception as exc:
                if "23505" in str(exc):
                    raise ValueError("DUPLICATE_REVIEW")
                raise
            if not insert_res.data:
                raise ValueError("Create failed")
            return insert_res.data[0]

        row = await asyncio.to_thread(validate_and_create)
        # Re-fetch with the users join so username is present
        enriched = await asyncio.to_thread(
            lambda: self.client.table("movie_reviews")
                .select(_REVIEW_SELECT)
                .eq("id", row["id"])
                .maybe_single()
                .execute()
        )
        return _flatten_user(dict(enriched.data)) if enriched.data else row

    async def update(self, review_id: int, review_in: dict, user_id: str) -> Optional[dict]:
        """Update review text or rating if owned by user."""
        await asyncio.to_thread(
            lambda: self.client.table("movie_reviews")
                .update(review_in)
                .eq("id", review_id)
                .eq("user_id", user_id)
                .execute()
        )
        # Re-fetch with users join
        response = await asyncio.to_thread(
            lambda: self.client.table("movie_reviews")
                .select(_REVIEW_SELECT)
                .eq("id", review_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
        )
        return _flatten_user(dict(response.data)) if response.data else None

    async def delete(self, review_id: int, user_id: str) -> bool:
        """Delete review if owned by user."""
        response = await asyncio.to_thread(
            lambda: self.client.table("movie_reviews")
                .delete()
                .eq("id", review_id)
                .eq("user_id", user_id)
                .execute()
        )
        return bool(response.data)

    async def add_like(self, review_id: int, user_id: str) -> dict:
        """Add a like to a review, increment like_count, and award milestone bonus to author."""
        def process_like():
            like_res = self.client.table("review_likes").insert({
                "review_id": review_id,
                "user_id": user_id,
            }).execute()

            if not like_res.data:
                raise ValueError("Already liked or failed")

            review = (
                self.client.table("movie_reviews")
                    .select("like_count, user_id")
                    .eq("id", review_id)
                    .single()
                    .execute()
            )
            new_count = (review.data.get("like_count") or 0) + 1
            author_id = review.data.get("user_id")
            self.client.table("movie_reviews").update({"like_count": new_count}).eq("id", review_id).execute()
            return like_res.data[0], new_count, author_id

        try:
            result, new_count, author_id = await asyncio.to_thread(process_like)
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise ValueError("Already liked")
            raise

        # Award milestone bonus to review author (only once per milestone)
        LIKE_MILESTONES = {10: 20, 50: 50, 100: 100}
        if author_id and new_count in LIKE_MILESTONES:
            try:
                milestone_reason = f"review_likes_{new_count}"
                already_res = await asyncio.to_thread(
                    lambda: self.client.table("membership_transactions")
                        .select("id", count="exact")
                        .eq("user_id", author_id)
                        .eq("reason", milestone_reason)
                        .eq("reference_id", str(review_id))
                        .execute()
                )
                if (already_res.count or 0) == 0:
                    bonus = LIKE_MILESTONES[new_count]
                    author_res = await asyncio.to_thread(
                        lambda: self.client.table("users")
                            .select("loyalty_points")
                            .eq("id", author_id)
                            .maybe_single()
                            .execute()
                    )
                    author_pts = (author_res.data or {}).get("loyalty_points") or 0
                    await asyncio.to_thread(
                        lambda: self.client.table("users")
                            .update({"loyalty_points": author_pts + bonus})
                            .eq("id", author_id)
                            .execute()
                    )
                    await asyncio.to_thread(
                        lambda: self.client.table("membership_transactions")
                            .insert({"user_id": author_id, "points_delta": bonus, "reason": milestone_reason, "reference_id": str(review_id)})
                            .execute()
                    )
            except Exception:
                pass  # Best-effort — never fail the like operation over bonus points

        return result

    async def remove_like(self, review_id: int, user_id: str) -> bool:
        """Remove a like from a review and decrement like_count."""
        def process_unlike():
            unlike_res = (
                self.client.table("review_likes")
                    .delete()
                    .eq("review_id", review_id)
                    .eq("user_id", user_id)
                    .execute()
            )
            if not unlike_res.data:
                return False

            review = (
                self.client.table("movie_reviews")
                    .select("like_count")
                    .eq("id", review_id)
                    .single()
                    .execute()
            )
            new_count = max(0, (review.data.get("like_count") or 0) - 1)
            self.client.table("movie_reviews").update({"like_count": new_count}).eq("id", review_id).execute()
            return True

        return await asyncio.to_thread(process_unlike)
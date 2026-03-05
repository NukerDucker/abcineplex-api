from supabase import Client
from typing import List, Optional
from app.schemas.movie import MovieCreate, MovieUpdate
import asyncio
import logging

logger = logging.getLogger(__name__)

# PostgREST select string that assembles all join-table arrays in one query
_MOVIE_SELECT = (
    "*, "
    "movie_cast(actor_name, display_order), "
    "movie_genres(genre), "
    "movie_audio_languages(language), "
    "movie_subtitle_languages(language)"
)


def _assemble(row: dict) -> dict:
    """
    Flatten the join-table sub-arrays back into the flat field names the
    rest of the app expects:
        movie_cast               → starring       (sorted by display_order)
        movie_genres             → genre          (list of strings)
        movie_audio_languages    → audio_languages
        movie_subtitle_languages → subtitle_languages
    """
    cast_rows = row.pop("movie_cast", None) or []
    genre_rows = row.pop("movie_genres", None) or []
    audio_rows = row.pop("movie_audio_languages", None) or []
    sub_rows = row.pop("movie_subtitle_languages", None) or []

    row["starring"] = [
        c["actor_name"]
        for c in sorted(cast_rows, key=lambda c: c.get("display_order", 0))
    ]
    row["genre"] = [g["genre"] for g in genre_rows]
    row["audio_languages"] = [a["language"] for a in audio_rows]
    row["subtitle_languages"] = [s["language"] for s in sub_rows]

    return row


class CRUDMovie:
    __slots__ = ("client",)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    # ── Join-table helpers ────────────────────────────────────

    async def _insert_cast(self, movie_id: int, starring: List[str]) -> None:
        if not starring:
            return
        data = [
            {"movie_id": movie_id, "actor_name": name, "display_order": idx}
            for idx, name in enumerate(starring)
        ]
        await asyncio.to_thread(
            lambda: self.client.table("movie_cast").insert(data).execute()
        )

    async def _insert_genres(self, movie_id: int, genres: List[str]) -> None:
        if not genres:
            return
        data = [{"movie_id": movie_id, "genre": g} for g in genres]
        await asyncio.to_thread(
            lambda: self.client.table("movie_genres").insert(data).execute()
        )

    async def _insert_audio_languages(self, movie_id: int, langs: List[str]) -> None:
        if not langs:
            return
        data = [{"movie_id": movie_id, "language": lang} for lang in langs]
        await asyncio.to_thread(
            lambda: self.client.table("movie_audio_languages").insert(data).execute()
        )

    async def _insert_subtitle_languages(self, movie_id: int, langs: List[str]) -> None:
        if not langs:
            return
        data = [{"movie_id": movie_id, "language": lang} for lang in langs]
        await asyncio.to_thread(
            lambda: self.client.table("movie_subtitle_languages").insert(data).execute()
        )

    async def _replace_join_tables(self, movie_id: int, data: dict) -> None:
        """
        For each array field present in an update payload: wipe the existing
        rows for that join table and re-insert. Simpler than diffing rows and
        safe because the tables are append-only metadata with no outward FKs.
        Mutates `data` in place by popping the handled keys.
        """
        if "starring" in data:
            await asyncio.to_thread(
                lambda: self.client.table("movie_cast")
                    .delete().eq("movie_id", movie_id).execute()
            )
            await self._insert_cast(movie_id, data.pop("starring") or [])

        if "genre" in data:
            await asyncio.to_thread(
                lambda: self.client.table("movie_genres")
                    .delete().eq("movie_id", movie_id).execute()
            )
            await self._insert_genres(movie_id, data.pop("genre") or [])

        if "audio_languages" in data:
            await asyncio.to_thread(
                lambda: self.client.table("movie_audio_languages")
                    .delete().eq("movie_id", movie_id).execute()
            )
            await self._insert_audio_languages(movie_id, data.pop("audio_languages") or [])

        if "subtitle_languages" in data:
            await asyncio.to_thread(
                lambda: self.client.table("movie_subtitle_languages")
                    .delete().eq("movie_id", movie_id).execute()
            )
            await self._insert_subtitle_languages(movie_id, data.pop("subtitle_languages") or [])

    # ── Write operations ──────────────────────────────────────

    async def create(self, movie: MovieCreate) -> dict:
        data = movie.model_dump(mode="json")

        # Extract join-table fields before inserting the movies row
        starring = data.pop("starring", []) or []
        genres = data.pop("genre", []) or []
        audio_langs = data.pop("audio_languages", []) or []
        sub_langs = data.pop("subtitle_languages", []) or []

        response = await asyncio.to_thread(
            lambda: self.client.table("movies").insert(data).execute()
        )
        movie_id = response.data[0]["id"]

        # Populate all join tables in parallel
        await asyncio.gather(
            self._insert_cast(movie_id, starring),
            self._insert_genres(movie_id, genres),
            self._insert_audio_languages(movie_id, audio_langs),
            self._insert_subtitle_languages(movie_id, sub_langs),
        )

        # Return the fully assembled record (scalar fields + joined arrays)
        return await self.get_by_id(movie_id)

    async def update(self, movie_id: int, movie_in: MovieUpdate) -> Optional[dict]:
        data = movie_in.model_dump(exclude_unset=True, mode="json")
        if not data:
            return await self.get_by_id(movie_id)

        # Handle join-table fields first; pops their keys from `data`
        await self._replace_join_tables(movie_id, data)

        # Only hit the movies table if there are scalar fields remaining
        if data:
            await asyncio.to_thread(
                lambda: self.client.table("movies")
                    .update(data)
                    .eq("id", movie_id)
                    .execute()
            )

        return await self.get_by_id(movie_id)

    async def delete(self, movie_id: int) -> bool:
        # Join tables have ON DELETE CASCADE — no manual cleanup needed
        response = await asyncio.to_thread(
            lambda: self.client.table("movies").delete().eq("id", movie_id).execute()
        )
        return bool(response.data)

    # ── Read operations ───────────────────────────────────────

    async def get_by_id(self, movie_id: int) -> Optional[dict]:
        response = await asyncio.to_thread(
            lambda: self.client.table("movies")
                .select(_MOVIE_SELECT)
                .eq("id", movie_id)
                .maybe_single()
                .execute()
        )
        if not response.data:
            return None
        return _assemble(dict(response.data))

    async def get_multi(
        self,
        page: int = 1,
        limit: int = 20,
        release_status: Optional[str] = None,
        active_only: bool = False,
    ) -> tuple[List[dict], int]:
        offset = (page - 1) * limit

        def _fetch():
            query = self.client.table("movies").select(_MOVIE_SELECT, count="exact")
            if release_status:
                query = query.eq("release_status", release_status)
            if active_only:
                query = query.eq("is_active", True)
            return query.range(offset, offset + limit - 1).execute()

        response = await asyncio.to_thread(_fetch)
        rows = [_assemble(dict(r)) for r in (response.data or [])]
        return rows, response.count or 0

    async def get_showtimes_for_movie(
        self,
        movie_id: int,
        from_date: str,
        to_date: str,
    ) -> List[dict]:
        """Get showtimes for a movie within [from_date, to_date], with theatre info."""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("showtimes")
                    .select("*, theatres(name, total_seats)")
                    .eq("movie_id", movie_id)
                    .gte("start_time", from_date)
                    .lte("start_time", to_date)
                    .order("start_time")
                    .execute()
            )
            return response.data or []
        except Exception as e:
            logger.warning(f"PostgREST join failed for showtimes: {e}. Falling back to manual join.")
            try:
                showtimes_response = await asyncio.to_thread(
                    lambda: self.client.table("showtimes")
                        .select("*")
                        .eq("movie_id", movie_id)
                        .gte("start_time", from_date)
                        .lte("start_time", to_date)
                        .order("start_time")
                        .execute()
                )
                showtimes_data = showtimes_response.data or []
                if not showtimes_data:
                    return []

                theatre_ids = list({st.get("theatre_id") for st in showtimes_data})
                theatres_response = await asyncio.to_thread(
                    lambda: self.client.table("theatres")
                        .select("id, name, total_seats")
                        .in_("id", theatre_ids)
                        .execute()
                )
                theatres_map = {t["id"]: t for t in (theatres_response.data or [])}
                for showtime in showtimes_data:
                    theatre_id = showtime.get("theatre_id")
                    if theatre_id in theatres_map:
                        showtime["theatres"] = theatres_map[theatre_id]
                return showtimes_data
            except Exception as fallback_error:
                logger.error(f"Failed to fetch showtimes for movie {movie_id}: {fallback_error}")
                return []
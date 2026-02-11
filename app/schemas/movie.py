from pydantic import BaseModel, HttpUrl
from datetime import date, datetime
from typing import List, Optional

class MovieBase(BaseModel):
    title: str
    release_date: date
    imdb_score: Optional[float] = None
    duration_minutes: int
    content_rating: str
    director: str
    starring: List[str]
    synopsis: str
    poster_url: HttpUrl
    banner_url: HttpUrl
    trailer_url: Optional[HttpUrl] = None
    audio_languages: List[str]
    subtitle_languages: List[str]
    tag_event: Optional[str] = None
    show_status: str

class MovieCreate(MovieBase):
    """Schema for creating a movie (request body)"""
    pass

class MovieUpdate(MovieBase):
    """Schema for updating (all fields optional)"""
    __annotations__ = {k: Optional[v] for k, v in MovieBase.__annotations__.items()}

class Movie(MovieBase):
    """Schema for reading data (response body)"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
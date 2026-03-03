from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class ReviewBase(BaseModel):
    movie_id: int
    review_text: str
    rating: float = Field(..., ge=1.0, le=5.0, description="Rating: 1.0 to 5.0")


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(BaseModel):
    review_text: Optional[str] = None
    rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="Rating: 1.0 to 5.0")


class ReviewResponse(BaseModel):
    id: int
    movie_id: int
    user_id: str
    username: Optional[str] = None
    review_text: Optional[str] = None
    rating: float
    like_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MovieSnippet(BaseModel):
    id: int
    title: str
    poster_url: Optional[str] = None
    release_date: Optional[str] = None


class ReviewWithMovie(ReviewResponse):
    """ReviewResponse enriched with movie info for community feed"""
    movie: Optional[MovieSnippet] = None


class ReviewListResponse(BaseModel):
    total: int
    items: List[ReviewResponse]


class ReviewWithMovieListResponse(BaseModel):
    total: int
    items: List[ReviewWithMovie]


class ReviewLikeResponse(BaseModel):
    id: int
    review_id: int
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class ReviewBase(BaseModel):
    movie_id: int
    booking_id: int
    review_text: str
    rating: int = Field(..., ge=1, le=5)


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(BaseModel):
    review_text: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)


class ReviewResponse(BaseModel):
    id: int
    movie_id: int
    booking_id: int
    user_id: str
    username: str
    review_text: str
    rating: int
    like_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    total: int
    items: List[ReviewResponse]


class ReviewLikeResponse(BaseModel):
    id: int
    review_id: int
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True

from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

# Common fields shared by both
class PublicContentBase(BaseModel):
    title: str
    is_active: bool = True

# --- Hero Carousel ---
class HeroSlideBase(PublicContentBase):
    banner_url: HttpUrl
    content_type: str # movie, event, link
    target_url: str   # path like /movies/uuid or external https://
    priority_order: int

class HeroSlide(HeroSlideBase):
    id: str
    created_at: datetime
    updated_at: datetime

# --- Promotions & News ---
class PromotionBase(PublicContentBase):
    image_url: HttpUrl
    promo_type: str # news, event, offer

class Promotion(PromotionBase):
    id: str
    created_at: datetime
    updated_at: datetime
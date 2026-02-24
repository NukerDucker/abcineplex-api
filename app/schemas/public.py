from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import Optional

# Common fields shared by both
class PublicContentBase(BaseModel):
    title: Optional[str] = None
    is_active: bool = True

# --- Hero Carousel ---
class HeroSlideBase(PublicContentBase):
    banner_url: Optional[str] = None
    content_type: Optional[str] = None
    target_url: Optional[str] = None
    display_order: Optional[int] = 0

class HeroSlideCreate(HeroSlideBase):
    pass

class HeroSlideUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    banner_url: Optional[HttpUrl] = None
    content_type: Optional[str] = None
    target_url: Optional[str] = None
    display_order: Optional[int] = None

class HeroSlide(HeroSlideBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# --- Promotions & News ---
class PromotionBase(PublicContentBase):
    image_url: Optional[str] = None
    promo_type: Optional[str] = None # news, event, offer

class PromotionCreate(PromotionBase):
    pass

class PromotionUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    image_url: Optional[str] = None
    promo_type: Optional[str] = None

class Promotion(PromotionBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
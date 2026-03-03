from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# Common fields shared by both
class PublicContentBase(BaseModel):
    title: Optional[str] = None
    is_active: bool = True

# --- Hero Carousel ---
class HeroSlideBase(PublicContentBase):
    image_url: str
    description: Optional[str] = None
    cta_link: Optional[str] = None
    cta_text: Optional[str] = None
    display_order: Optional[int] = 0

class HeroSlideCreate(HeroSlideBase):
    pass

class HeroSlideUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    cta_link: Optional[str] = None
    cta_text: Optional[str] = None
    display_order: Optional[int] = None

class HeroSlide(HeroSlideBase):
    id: str
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
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
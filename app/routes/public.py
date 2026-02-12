from fastapi import APIRouter
from typing import List
from app.crud.public import CRUDPublic
from app.schemas.public import HeroSlide, HeroSlideCreate, HeroSlideUpdate, Promotion, PromotionCreate, PromotionUpdate
from app.core.supabase import supabase
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/api", tags=["public"])
crud_public = CRUDPublic(supabase)


@router.post("/hero-carousel", response_model=HeroSlide)
async def create_hero_slide(slide: HeroSlideCreate):
    """Create hero carousel slide"""
    return await crud_public.create_hero_slide(slide)


@router.put("/hero-carousel/{slide_id}", response_model=HeroSlide)
async def update_hero_slide(slide_id: str, slide: HeroSlideUpdate):
    """Update hero carousel slide"""
    updated = await crud_public.update_hero_slide(slide_id, slide)
    if not updated:
        raise NotFoundException("Hero slide", slide_id)
    return updated


@router.delete("/hero-carousel/{slide_id}")
async def delete_hero_slide(slide_id: str):
    """Delete hero carousel slide"""
    success = await crud_public.delete_hero_slide(slide_id)
    if not success:
        raise NotFoundException("Hero slide", slide_id)
    return {"status": "success"}


@router.get("/hero-carousel", response_model=List[HeroSlide])
async def get_hero_carousel():
    """Get active hero carousel slides ordered by display priority"""
    return await crud_public.get_hero_carousel()


@router.post("/promo-events", response_model=Promotion)
async def create_promotion(promo: PromotionCreate):
    """Create promotional event"""
    return await crud_public.create_promotion(promo)


@router.put("/promo-events/{promo_id}", response_model=Promotion)
async def update_promotion(promo_id: str, promo: PromotionUpdate):
    """Update promotional event"""
    updated = await crud_public.update_promotion(promo_id, promo)
    if not updated:
        raise NotFoundException("Promotion", promo_id)
    return updated


@router.delete("/promo-events/{promo_id}")
async def delete_promotion(promo_id: str):
    """Delete promotional event"""
    success = await crud_public.delete_promotion(promo_id)
    if not success:
        raise NotFoundException("Promotion", promo_id)
    return {"status": "success"}


@router.get("/promo-events", response_model=List[Promotion])
async def get_promo_events():
    """Get active promotional events"""
    return await crud_public.get_promo_events()

from fastapi import APIRouter
from typing import List
from app.crud.public import CRUDPublic
from app.schemas.public import HeroSlide, Promotion
from app.core.supabase import supabase_admin

router = APIRouter(prefix="/api/v1", tags=["public"])
crud_public = CRUDPublic(supabase_admin)


@router.get("/hero-carousel", response_model=List[HeroSlide])
async def get_hero_carousel():
    """Get active hero carousel slides ordered by display priority"""
    return await crud_public.get_hero_carousel()


@router.get("/promo-events", response_model=List[Promotion])
async def get_promo_events():
    """Get active promotional events"""
    return await crud_public.get_promo_events()

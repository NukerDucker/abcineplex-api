from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.crud.public import CRUDPublic
from app.schemas.public import HeroSlide, HeroSlideCreate, HeroSlideUpdate, Promotion, PromotionCreate, PromotionUpdate
from app.core.supabase import supabase

router = APIRouter(prefix="/api", tags=["public"])
crud_public = CRUDPublic(supabase)

# --- Hero Carousel ---
@router.post("/hero-carousel", response_model=HeroSlide)
async def create_hero_slide(slide: HeroSlideCreate):
    try:
        return await crud_public.create_hero_slide(slide)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/hero-carousel/{slide_id}", response_model=HeroSlide)
async def update_hero_slide(slide_id: str, slide: HeroSlideUpdate):
    try:
        updated = await crud_public.update_hero_slide(slide_id, slide)
        if not updated:
            raise HTTPException(status_code=404, detail="Slide not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/hero-carousel/{slide_id}")
async def delete_hero_slide(slide_id: str):
    success = await crud_public.delete_hero_slide(slide_id)
    if not success:
        raise HTTPException(status_code=404, detail="Slide not found")
    return {"status": "success"}

@router.get("/hero-carousel", response_model=List[HeroSlide])
async def get_hero_carousel():
    """
    Get the hero carousel slides for the homepage
    Returns active carousel items ordered by display priority
    """
    try:
        carousel = await crud_public.get_hero_carousel()
        if not carousel:
            return []  # Return empty array if no carousel items
        return carousel
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching carousel: {str(e)}")

# --- Promotions ---
@router.post("/promo-events", response_model=Promotion)
async def create_promotion(promo: PromotionCreate):
    try:
        return await crud_public.create_promotion(promo)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/promo-events/{promo_id}", response_model=Promotion)
async def update_promotion(promo_id: str, promo: PromotionUpdate):
    try:
        updated = await crud_public.update_promotion(promo_id, promo)
        if not updated:
            raise HTTPException(status_code=404, detail="Promotion not found")
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/promo-events/{promo_id}")
async def delete_promotion(promo_id: str):
    success = await crud_public.delete_promotion(promo_id)
    if not success:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return {"status": "success"}

@router.get("/promo-events", response_model=List[Promotion])
async def get_promo_events():
    """
    Get promotional events and news
    Returns active events and news items
    """
    try:
        events = await crud_public.get_promo_events()
        if not events:
            return []  # Return empty array if no events
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching promo events: {str(e)}")

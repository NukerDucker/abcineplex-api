from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.crud.public import CRUDPublic
from app.core.supabase import supabase

router = APIRouter(prefix="/api", tags=["public"])
crud_public = CRUDPublic(supabase)


@router.get("/hero-carousel", response_model=List[Dict[str, Any]])
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


@router.get("/promo-events", response_model=List[Dict[str, Any]])
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

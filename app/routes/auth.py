from fastapi import APIRouter, Depends
from app.schemas.auth import UserResponse
from app.core.security import get_current_user, CurrentUser

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: CurrentUser = Depends(get_current_user)):
    """
    Get current authenticated user information.
    Optimized: No additional DB calls needed - data comes from security dependency.
    """
    return UserResponse(
        user_id=str(current_user.user_id),
        email=current_user.email,
        user_name=current_user.user_name,
        full_name=current_user.full_name,
        loyalty_points=current_user.loyalty_points
    )
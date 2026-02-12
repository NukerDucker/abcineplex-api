"""
Auth API Routes
Handles authentication endpoints (login, register, token refresh)
"""
from fastapi import APIRouter, HTTPException, status, Depends
from datetime import timedelta

from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.crud.user import CRUDUser
from app.core.supabase import supabase
from app.core.security import create_access_token, get_current_user
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
crud_user = CRUDUser(supabase)


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    """
    Authenticate user and return JWT token
    """
    try:
        # Get user by email
        user = crud_user.get_by_email(request.email)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Verify password
        if not crud_user.verify_password(request.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Check if user is active
        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is deactivated"
            )

        # Create access token
        access_token = create_access_token(
            data={
                "sub": str(user["user_id"]),
                "email": user["email"],
                "is_admin": user.get("is_admin", False)
            },
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
        )

        # Return token and user info (without sensitive data)
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user={
                "user_id": user["user_id"],
                "email": user["email"],
                "user_name": user["user_name"],
                "full_name": user["full_name"],
                "phone": user.get("phone"),
                "loyalty_points": user.get("loyalty_points", 0)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during login"
        )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest):
    """
    Register a new user and return JWT token
    """
    try:
        # Check if email already exists
        existing_user = crud_user.get_by_email(request.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Create user
        user_data = {
            "email": request.email,
            "password": request.password,
            "user_name": request.user_name,
            "full_name": request.full_name,
            "phone": request.phone or ""
        }

        new_user = crud_user.create(user_data)

        # Create access token
        access_token = create_access_token(
            data={
                "sub": str(new_user["user_id"]),
                "email": new_user["email"],
                "is_admin": False
            },
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
        )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user={
                "user_id": new_user["user_id"],
                "email": new_user["email"],
                "user_name": new_user["user_name"],
                "full_name": new_user["full_name"],
                "phone": new_user.get("phone"),
                "loyalty_points": new_user.get("loyalty_points", 0)
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration"
        )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user info
    """
    try:
        user = crud_user.get_by_id(
            user_id=current_user["user_id"],
            current_user_id=current_user["user_id"],
            is_admin=current_user.get("is_admin", False)
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return UserResponse(
            user_id=user["user_id"],
            email=user["email"],
            user_name=user["user_name"],
            full_name=user["full_name"],
            phone=user.get("phone"),
            loyalty_points=user.get("loyalty_points", 0)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get user error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred"
        )


@router.post("/logout")
def logout():
    """
    Logout endpoint (client should discard the token)
    """
    return {"message": "Successfully logged out"}

from fastapi import APIRouter, Depends
import asyncio
import logging

from app.schemas.auth import (
    RegisterRequest, RegisterResponse,
    LoginRequest, LoginResponse, TokenUser,
    RefreshRequest, RefreshResponse,
)
from app.core.supabase import supabase, supabase_admin
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import AppException, AuthenticationException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest):
    """Register a new user account."""
    # 1. Create auth user via Supabase Auth
    try:
        auth_res = await asyncio.to_thread(
            lambda: supabase.auth.sign_up({"email": body.email, "password": body.password})
        )
    except Exception as e:
        logger.error(f"Supabase sign_up failed: {e}")
        raise AppException("Registration failed", 400)

    if not auth_res.user:
        raise AppException("Email already registered", 409)

    user_id = str(auth_res.user.id)
    token = auth_res.session.access_token if auth_res.session else ""

    # 2. Insert profile row — maps spec fields to existing DB columns
    full_name = f"{body.first_name} {body.last_name}".strip()
    try:
        await asyncio.to_thread(
            lambda: supabase_admin.table("users").insert({
                "user_id": user_id,
                "email": body.email,
                "full_name": full_name,
                "user_name": body.email.split("@")[0],
                "phone": body.phone,
                "loyalty_points": 0,
                "is_admin": False,
            }).execute()
        )
    except Exception as e:
        logger.error(f"Failed to insert user profile: {e}")
        # Auth user was created; profile insert failed — not fatal, log and continue

    return RegisterResponse(message="Registration successful", user_id=user_id, token=token)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Login with email and password."""
    try:
        auth_res = await asyncio.to_thread(
            lambda: supabase.auth.sign_in_with_password(
                {"email": body.email, "password": body.password}
            )
        )
    except Exception as e:
        logger.warning(f"Login failed for {body.email}: {e}")
        raise AuthenticationException("Invalid credentials")

    if not auth_res.session:
        raise AuthenticationException("Invalid credentials")

    # Fetch profile
    profile_res = await asyncio.to_thread(
        lambda: supabase_admin.table("users")
            .select("user_id, full_name, loyalty_points")
            .eq("user_id", str(auth_res.user.id))
            .maybe_single()
            .execute()
    )
    profile = profile_res.data or {}
    full_name = profile.get("full_name", "")
    first_name = full_name.split(" ")[0] if full_name else ""

    return LoginResponse(
        token=auth_res.session.access_token,
        refresh_token=auth_res.session.refresh_token,
        user=TokenUser(
            id=str(auth_res.user.id),
            email=auth_res.user.email or body.email,
            first_name=first_name,
            membership_tier="free",
            reward_points=profile.get("loyalty_points", 0),
        ),
    )


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Invalidate current session token."""
    try:
        await asyncio.to_thread(lambda: supabase.auth.sign_out())
    except Exception:
        pass  # Best-effort; token expiry handles the rest
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(body: RefreshRequest):
    """Refresh JWT access token using a refresh token."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase.auth.refresh_session(body.refresh_token)
        )
    except Exception as e:
        logger.warning(f"Token refresh failed: {e}")
        raise AuthenticationException("Invalid or expired refresh token")

    if not result.session:
        raise AuthenticationException("Invalid or expired refresh token")

    return RefreshResponse(
        token=result.session.access_token,
        refresh_token=result.session.refresh_token,
    )

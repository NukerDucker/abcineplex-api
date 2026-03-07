import asyncio
import logging
import os

import bcrypt
from fastapi import APIRouter, Depends

from app.core.exceptions import AppException, AuthenticationException
from app.core.security import CurrentUser, get_current_user
from app.core.supabase import supabase, supabase_admin
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    SetPasswordRequest,
    SetupInfoRequest,
    TokenUser,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ── Helpers ──────────────────────────────────────────────────────────────────

_PROFILE_SELECT = (
    "id, full_name, user_name, loyalty_points, is_admin, "
    "phone, date_of_birth, is_student, student_id_verified, "
    "password_hash"
)


def _build_token_user(user_id: str, email: str, profile: dict) -> TokenUser:
    """Build a TokenUser from a raw DB profile dict."""
    full_name = str(profile.get("full_name", "") or "")

    email_prefix = email.split("@")[0] if "@" in email else "user"
    user_name = str(profile.get("user_name", "") or email_prefix)

    phone: str | None = str(profile["phone"]) if profile.get("phone") else None
    date_of_birth: str | None = str(profile["date_of_birth"]) if profile.get("date_of_birth") else None

    return TokenUser(
        id=user_id,
        email=email,
        user_name=user_name,
        full_name=full_name,
        is_admin=bool(profile.get("is_admin", False)),
        phone=phone,
        date_of_birth=date_of_birth,
        is_student=bool(profile.get("is_student", False)),
        student_id_verified=bool(profile.get("student_id_verified", False)),
        membership_tier="free",
        reward_points=int(profile.get("loyalty_points", 0) or 0),
        has_password=bool(profile.get("password_hash")),
    )


async def _fetch_profile(user_id: str) -> dict:
    """Fetch user profile from DB. Returns empty dict if not found."""
    logger.debug(f"[auth] _fetch_profile: querying DB for user_id={user_id}")
    try:
        res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select(_PROFILE_SELECT)
                .eq("id", user_id)
                .maybe_single()
                .execute()
        )
        data = res.data if res else None
        logger.debug(f"[auth] _fetch_profile: res.data type={type(data).__name__}, value={data}")
        if res and res.data and isinstance(res.data, dict):
            logger.debug(f"[auth] _fetch_profile: returning profile — has_password={bool(res.data.get('password_hash'))}")
            return res.data
        logger.warning(f"[auth] _fetch_profile: no profile row found for user_id={user_id}")
    except Exception as e:
        logger.warning(f"[auth] _fetch_profile: exception for user_id={user_id}: {e}", exc_info=True)
    return {}


# ── Register ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest):
    """
    Register a new user with email/password.

    Flow:
    1. Call Supabase Auth sign_up (passes full_name in metadata for the trigger)
    2. DB trigger auto-creates public.users row with {id, email, full_name, avatar_url}
    3. Backend UPDATEs the row with user_name, phone, date_of_birth, password_hash
    4. If a session was returned (no email confirmation required), auto-login the user
    """
    logger.info(f"[auth] register: email={body.email}")
    full_name = body.full_name.strip()

    # 1. Create auth user — trigger will insert into public.users
    try:
        auth_res = await asyncio.to_thread(
            lambda: supabase.auth.sign_up({
                "email": body.email,
                "password": body.password,
                "options": {"data": {"full_name": full_name}},
            })
        )
        logger.debug(f"[auth] register: sign_up result — user_id={getattr(auth_res.user, 'id', None)}, has_session={auth_res.session is not None}")
    except Exception as e:
        logger.error(f"[auth] register: sign_up exception: {e}", exc_info=True)
        raise AppException("Registration failed", 400)

    if not auth_res.user:
        logger.warning("[auth] register: sign_up returned no user — email likely already registered")
        raise AppException("Email already registered or registration failed", 409)

    user_id = str(auth_res.user.id)
    logger.info(f"[auth] register: auth user created — user_id={user_id}")

    # 2. Hash password and UPDATE the trigger-created row with extra fields
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    email_prefix = body.email.split("@")[0]

    update_data: dict = {
        "user_name": email_prefix,
        "password_hash": password_hash,
    }
    if body.phone:
        update_data["phone"] = body.phone
    if body.date_of_birth:
        update_data["date_of_birth"] = body.date_of_birth.isoformat()

    logger.debug(f"[auth] register: updating public.users with fields: {list(update_data.keys())}")
    try:
        update_res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .update(update_data)
                .eq("id", user_id)
                .execute()
        )
        logger.debug(f"[auth] register: profile UPDATE result — data={update_res.data}")
    except Exception as e:
        logger.error(f"[auth] register: profile UPDATE exception: {e}", exc_info=True)
        # Not fatal — user is created, profile incomplete

    # 3. No session → email confirmation required
    if not auth_res.session:
        logger.info("[auth] register: no session returned — email confirmation required")
        return RegisterResponse(
            message="Registration successful. Please check your email to confirm your account.",
            requires_confirmation=True,
        )

    # 4. Session available → fetch full profile and auto-login
    profile = await _fetch_profile(user_id)
    email = str(auth_res.user.email or body.email)
    token_user = _build_token_user(user_id, email, profile)

    # EP-20: Record referral relationship — points awarded after referred user's first confirmed booking
    if body.referral_code:
        try:
            ref_res = await asyncio.to_thread(
                lambda: supabase_admin.table("users")
                    .select("id")
                    .eq("user_name", body.referral_code)
                    .maybe_single()
                    .execute()
            )
            if ref_res.data and ref_res.data["id"] != user_id:
                referrer_id = ref_res.data["id"]
                # Store pending referral — _apply_loyalty will convert this to real points on first booking
                await asyncio.to_thread(
                    lambda: supabase_admin.table("membership_transactions")
                        .insert({"user_id": user_id, "points_delta": 0, "reason": "referral_pending", "reference_id": referrer_id})
                        .execute()
                )
                logger.info(f"[auth] referral: pending referral recorded for new user {user_id}, referrer {referrer_id}")
        except Exception as e:
            logger.warning(f"[auth] referral pending record failed: {e}")

    logger.info(f"[auth] register: auto-login success for user_id={user_id}")

    return RegisterResponse(
        message="Registration successful.",
        token=auth_res.session.access_token,
        refresh_token=auth_res.session.refresh_token,
        user=token_user,
    )


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    """Login with email and password."""
    logger.info(f"[auth] login: email={body.email}")
    try:
        auth_res = await asyncio.to_thread(
            lambda: supabase.auth.sign_in_with_password(
                {"email": body.email, "password": body.password}
            )
        )
        logger.debug(f"[auth] login: sign_in result — user_id={getattr(auth_res.user, 'id', None)}, has_session={auth_res.session is not None}")
    except Exception as e:
        logger.warning(f"[auth] login: sign_in exception for {body.email}: {e}")
        raise AuthenticationException("Invalid credentials")

    if not auth_res.session or not auth_res.user:
        logger.warning(f"[auth] login: no session/user returned for {body.email}")
        raise AuthenticationException("Invalid credentials")

    user_id = str(auth_res.user.id)
    email = str(auth_res.user.email or body.email)
    logger.info(f"[auth] login: auth success for user_id={user_id}")

    profile = await _fetch_profile(user_id)
    logger.debug(f"[auth] login: profile has_password={bool(profile.get('password_hash'))}")

    return LoginResponse(
        token=auth_res.session.access_token,
        refresh_token=auth_res.session.refresh_token,
        user=_build_token_user(user_id, email, profile),
    )


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Invalidate current session token."""
    logger.info(f"[auth] logout: user_id={current_user.user_id}")
    try:
        await asyncio.to_thread(lambda: supabase.auth.sign_out())
    except Exception:
        pass  # Best-effort; token expiry handles the rest
    return {"message": "Logged out successfully"}


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(body: RefreshRequest):
    """Refresh JWT access token using a refresh token."""
    logger.debug("[auth] refresh_token called")
    try:
        result = await asyncio.to_thread(
            lambda: supabase.auth.refresh_session(body.refresh_token)
        )
        logger.debug(f"[auth] refresh_token: has_session={result.session is not None}")
    except Exception as e:
        logger.warning(f"[auth] refresh_token: exception: {e}")
        raise AuthenticationException("Invalid or expired refresh token")

    if not result.session:
        raise AuthenticationException("Invalid or expired refresh token")

    return RefreshResponse(
        token=result.session.access_token,
        refresh_token=result.session.refresh_token,
    )


# ── Set password ──────────────────────────────────────────────────────────────

@router.post("/set-password")
async def set_password(
    body: SetPasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Set or update password for authenticated user.

    Required for Google OAuth users who sign in for the first time — they
    won't have a password_hash and the frontend redirects them here.
    Also usable by credential users to change their password.
    """
    logger.info(f"[auth] set_password: user_id={current_user.user_id}")
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    # Update Supabase Auth password so credential login works
    try:
        logger.debug(f"[auth] set_password: calling admin.update_user_by_id for {current_user.user_id}")
        auth_update = await asyncio.to_thread(
            lambda: supabase_admin.auth.admin.update_user_by_id(
                current_user.user_id,
                {"password": body.password},
            )
        )
        updated_user = getattr(auth_update, "user", None)
        logger.debug(f"[auth] set_password: Supabase auth password updated — user_id={getattr(updated_user, 'id', None)}")
        if not updated_user:
            logger.error("[auth] set_password: update_user_by_id returned no user")
            raise AppException("Failed to set password in auth", 500)
    except AppException:
        raise
    except Exception as e:
        logger.error(f"[auth] set_password: failed to update Supabase auth password: {e}", exc_info=True)
        raise AppException("Failed to set password", 500)

    # Store hash in public.users
    try:
        logger.debug(f"[auth] set_password: updating password_hash in public.users for {current_user.user_id}")
        update_res = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .update({"password_hash": password_hash})
                .eq("id", current_user.user_id)
                .execute()
        )
        logger.debug(f"[auth] set_password: DB update result — data={update_res.data}")
    except Exception as e:
        logger.error(f"[auth] set_password: failed to store password hash: {e}", exc_info=True)
        raise AppException("Failed to set password", 500)

    logger.info(f"[auth] set_password: success for user_id={current_user.user_id}")
    return {"message": "Password set successfully"}


# ── Setup info (OAuth onboarding) ─────────────────────────────────────────────

@router.post("/setup-info")
async def setup_info(
    body: SetupInfoRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Complete profile setup for OAuth users on first sign-in.

    Sets password (required) plus optional user_name, phone, date_of_birth.
    """
    logger.info(f"[auth] setup_info: user_id={current_user.user_id}")
    password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()

    # Update Supabase Auth password so credential login works
    try:
        auth_update = await asyncio.to_thread(
            lambda: supabase_admin.auth.admin.update_user_by_id(
                current_user.user_id,
                {"password": body.password},
            )
        )
        updated_user = getattr(auth_update, "user", None)
        logger.debug(f"[auth] setup_info: Supabase auth password updated — user_id={getattr(updated_user, 'id', None)}")
        if not updated_user:
            logger.error("[auth] setup_info: update_user_by_id returned no user")
            raise AppException("Failed to set password in auth", 500)
    except AppException:
        raise
    except Exception as e:
        logger.error(f"[auth] setup_info: failed to update Supabase auth password: {e}", exc_info=True)
        raise AppException("Failed to set password", 500)

    # Build update payload for public.users
    update_data: dict = {"password_hash": password_hash}
    if body.user_name:
        update_data["user_name"] = body.user_name
    if body.phone:
        update_data["phone"] = body.phone
    if body.date_of_birth:
        update_data["date_of_birth"] = body.date_of_birth.isoformat()

    try:
        await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .update(update_data)
                .eq("id", current_user.user_id)
                .execute()
        )
        logger.debug(f"[auth] setup_info: DB update OK — fields={list(update_data.keys())}")
    except Exception as e:
        logger.error(f"[auth] setup_info: failed to update public.users: {e}", exc_info=True)
        raise AppException("Failed to save profile info", 500)

    logger.info(f"[auth] setup_info: success for user_id={current_user.user_id}")
    return {"message": "Profile setup complete"}


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google")
async def google_signin():
    """Return the Supabase Google OAuth URL for the frontend to redirect to."""
    try:
        from urllib.parse import quote
        redirect_url = os.getenv("SUPABASE_REDIRECT_URL", "http://localhost:3000/auth/callback")
        supabase_url = os.getenv("SUPABASE_URL", "")
        google_url = (
            f"{supabase_url}/auth/v1/authorize?"
            f"provider=google&"
            f"redirect_to={quote(redirect_url, safe='')}&"
            f"response_type=code&"
            f"scope=openid%20profile%20email"
        )
        logger.debug(f"[auth] google_signin: returning URL (redirect_url={redirect_url})")
        return {"url": google_url}
    except Exception as e:
        logger.error(f"[auth] google_signin: URL generation failed: {e}", exc_info=True)
        raise AppException("Failed to initiate Google signin", 500)

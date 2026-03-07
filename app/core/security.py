import asyncio
import logging

import jwt as pyjwt
from jwt import PyJWKClient
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.exceptions import AuthenticationException
from app.core.supabase import supabase_admin

logger = logging.getLogger(__name__)
security = HTTPBearer()

# JWKS client for asymmetric (RS256/ES256) Supabase projects — cached at module level
_jwks_client = PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")

_SYMMETRIC_ALGS = {"HS256", "HS384", "HS512"}
_ASYMMETRIC_ALGS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}


class CurrentUser:
    __slots__ = ('user_id', 'email', 'full_name', 'user_name', 'loyalty_points', 'is_admin')

    def __init__(self, user_id: str, email: str, full_name: str = "",
                 user_name: str = "", loyalty_points: int = 0, is_admin: bool = False):
        self.user_id = user_id
        self.email = email
        self.full_name = full_name
        self.user_name = user_name
        self.loyalty_points = loyalty_points
        self.is_admin = is_admin


def _decode_jwt(token: str) -> dict:
    """
    Verify the JWT and return the payload.

    Tries symmetric verification (HS256) first — the Supabase default.
    If the token uses an asymmetric algorithm (RS256, ES256/P-256, etc.),
    PyJWT raises InvalidAlgorithmError and we fall back to JWKS verification.
    This avoids reading the unverified header to determine the algorithm.
    """
    # Allow up to 60 seconds of clock skew between this server and Supabase
    _LEEWAY = 300

    # Attempt 1: symmetric signing (HS256 — Supabase default)
    try:
        return pyjwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=list(_SYMMETRIC_ALGS),
            audience="authenticated",
            leeway=_LEEWAY,
            options={"verify_iat": True}
        )
    except pyjwt.exceptions.InvalidAlgorithmError:
        pass  # Token uses an asymmetric algorithm — try JWKS below
    except pyjwt.ExpiredSignatureError:
        logger.warning("[security] JWT expired")
        raise AuthenticationException("Token expired")
    except pyjwt.InvalidTokenError as e:
        logger.warning(f"[security] JWT invalid (symmetric): {e}")
        raise AuthenticationException("Invalid token")

    # Attempt 2: asymmetric signing via JWKS (RS256, ES256/P-256, etc.)
    logger.debug("[security] Symmetric verification failed — trying JWKS (asymmetric)")
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=list(_ASYMMETRIC_ALGS),
            audience="authenticated",
            leeway=_LEEWAY,
        )
    except pyjwt.ExpiredSignatureError:
        logger.warning("[security] JWT expired")
        raise AuthenticationException("Token expired")
    except pyjwt.InvalidTokenError as e:
        logger.warning(f"[security] JWT invalid (asymmetric): {e}")
        raise AuthenticationException("Invalid token")


async def _fetch_db_profile(user_id: str) -> dict | None:
    """Return the public.users row for user_id, or None on any failure."""
    try:
        result = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select("id, email, full_name, user_name, loyalty_points, is_admin, is_active")
                .eq("id", user_id)
                .limit(1)
                .execute()
        )
        data = result.data if result else None
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
    except Exception as e:
        logger.warning(f"[security] Could not fetch DB profile for {user_id}: {e}")
    return None


def _current_user_from_db(db_user: dict, fallback_id: str, fallback_email: str) -> CurrentUser:
    return CurrentUser(
        user_id=str(db_user.get("id", fallback_id)),
        email=str(db_user.get("email", fallback_email)),
        full_name=str(db_user.get("full_name", "") or ""),
        user_name=str(db_user.get("user_name", "") or ""),
        loyalty_points=int(db_user.get("loyalty_points", 0) or 0),
        is_admin=bool(db_user.get("is_admin", False)),
    )


def _current_user_from_jwt(payload: dict, user_id: str, email: str) -> CurrentUser:
    user_meta: dict = payload.get("user_metadata", {}) or {}
    raw_name = user_meta.get("full_name") or user_meta.get("name") or ""
    return CurrentUser(
        user_id=user_id,
        email=email,
        full_name=raw_name if isinstance(raw_name, str) else "",
        user_name=email.split("@")[0] if email else "user",
        loyalty_points=0,
        is_admin=False,
    )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> CurrentUser:
    token = credentials.credentials
    logger.debug(f"[security] get_current_user — token preview: {token[:20]}...")

    # Step 1: Verify JWT locally (no session lookup — avoids AuthApiError for OAuth tokens)
    payload = _decode_jwt(token)
    user_id: str = payload.get("sub", "")
    email: str = payload.get("email", "")
    logger.debug(f"[security] JWT decoded — user_id={user_id}, email={email}")

    if not user_id:
        raise AuthenticationException("Invalid token: missing subject")

    # Step 2: Look up profile in public.users
    db_user = await _fetch_db_profile(user_id)

    if db_user:
        if not db_user.get("is_active", True):
            raise AuthenticationException("Account has been deactivated")
        logger.debug(f"[security] Returning CurrentUser from DB — user_id={user_id}, is_admin={db_user.get('is_admin')}")
        return _current_user_from_db(db_user, user_id, email)

    # Fallback: profile not in DB yet (trigger hasn't fired or race condition)
    logger.warning(f"[security] Profile not in DB for {user_id} — using JWT claims as fallback")
    return _current_user_from_jwt(payload, user_id, email)


_optional_bearer = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> CurrentUser | None:
    """Like get_current_user but returns None instead of 401 when no token is supplied."""
    if not credentials:
        return None
    try:
        payload = _decode_jwt(credentials.credentials)
        user_id: str = payload.get("sub", "")
        if not user_id:
            return None
        email: str = payload.get("email", "")
        db_user = await _fetch_db_profile(user_id)
        if db_user:
            if not db_user.get("is_active", True):
                return None
            return _current_user_from_db(db_user, user_id, email)
        return _current_user_from_jwt(payload, user_id, email)
    except Exception:
        return None


async def get_admin_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency to ensure user is authenticated and has admin privileges"""
    from app.core.exceptions import UnauthorizedException
    if not current_user.is_admin:
        raise UnauthorizedException("Admin privileges required")
    return current_user

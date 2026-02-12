from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import supabase
from app.core.exceptions import AuthenticationException
import asyncio
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer()


class CurrentUser:
    """Optimized user data structure"""
    __slots__ = ('user_id', 'email', 'full_name', 'user_name', 'loyalty_points', 'is_admin')

    def __init__(self, user_id: str, email: str, full_name: str = "",
                 user_name: str = "", loyalty_points: int = 0, is_admin: bool = False):
        self.user_id = user_id
        self.email = email
        self.full_name = full_name
        self.user_name = user_name
        self.loyalty_points = loyalty_points
        self.is_admin = is_admin


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> CurrentUser:
    """
    One-trip optimized authentication dependency.
    Non-blocking async calls to prevent frontend hangs.
    """
    token = credentials.credentials

    try:
        # Verify token and get Supabase user (non-blocking)
        user_response = await asyncio.to_thread(lambda: supabase.auth.get_user(token))
        supabase_user = user_response.user

        if not supabase_user or not supabase_user.email:
            raise AuthenticationException("Invalid or expired token")

        metadata = supabase_user.user_metadata or {}

        # Try to get DB profile (single non-blocking query)
        try:
            # Note: is_admin is checked from user_metadata first as the column might not exist in users table
            result = await asyncio.to_thread(
                lambda: supabase.table("users")
                    .select("user_id, loyalty_points")
                    .eq("email", supabase_user.email)
                    .execute()
            )

            db_user = result.data[0] if result.data and len(result.data) > 0 else None
        except Exception as e:
            logger.warning(f"Could not fetch user profile for {supabase_user.email}: {e}")
            db_user = None

        # Admin status can come from metadata (Supabase) or DB
        is_admin = metadata.get("is_admin", False)
        if not is_admin and db_user:
            is_admin = db_user.get("is_admin", False)

        # Build optimized user object
        return CurrentUser(
            user_id=supabase_user.id,
            email=supabase_user.email,
            full_name=metadata.get("full_name", ""),
            user_name=metadata.get("user_name", supabase_user.email.split("@")[0]),
            loyalty_points=db_user.get("loyalty_points", 0) if db_user else 0,
            is_admin=is_admin
        )

    except AuthenticationException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise AuthenticationException("Authentication failed")
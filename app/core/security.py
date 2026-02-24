from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import supabase
from app.core.exceptions import AuthenticationException
import asyncio
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer()

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


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> CurrentUser:
    token = credentials.credentials

    try:
        user_response = await asyncio.to_thread(lambda: supabase.auth.get_user(token))
        supabase_user = user_response.user

        if not supabase_user or not supabase_user.email:
            raise AuthenticationException("Invalid or expired token")

        metadata = supabase_user.user_metadata or {}

        try:
            # Fetch user record from users table
            result = await asyncio.to_thread(
                lambda: supabase.table("users")
                    .select("loyalty_points, is_admin")
                    .eq("email", supabase_user.email)
                    .execute()
            )

            db_user = result.data[0] if result.data and len(result.data) > 0 else None
        except Exception as e:
            logger.warning(f"Could not fetch user record for {supabase_user.email}: {e}")
            db_user = None

        is_admin = metadata.get("is_admin", False)
        if db_user:
            is_admin = db_user.get("is_admin", is_admin)

        logger.info(f"User {supabase_user.email} - is_admin from metadata: {metadata.get('is_admin', False)}, from users table: {db_user.get('is_admin') if db_user else 'N/A'}, final: {is_admin}")

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


async def get_admin_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency to ensure user is authenticated and has admin privileges"""
    if not current_user.is_admin:
        raise AuthenticationException("Admin privileges required")
    return current_user
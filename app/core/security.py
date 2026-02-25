from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import supabase, supabase_admin
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
        # Step 1: Verify JWT and extract the user UUID
        auth_response = await asyncio.to_thread(lambda: supabase.auth.get_user(token))
        auth_user = auth_response.user
        if not auth_user or not auth_user.id:
            raise AuthenticationException("Invalid or expired token")

        # Step 2: Use UUID to look up the user record in the users table
        result = await asyncio.to_thread(
            lambda: supabase_admin.table("users")
                .select("user_id, email, full_name, user_name, loyalty_points, is_admin")
                .eq("user_id", auth_user.id)
                .limit(1)
                .execute()
        )
        if not result or not result.data:
            raise AuthenticationException("User not found")

        db_user = result.data[0]

        return CurrentUser(
            user_id=db_user["user_id"],
            email=db_user["email"],
            full_name=db_user.get("full_name", ""),
            user_name=db_user.get("user_name", ""),
            loyalty_points=db_user.get("loyalty_points", 0),
            is_admin=db_user.get("is_admin", False),
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
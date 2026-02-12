"""
Security utilities for Supabase JWT token verification
"""
from typing import Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.supabase import supabase
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get current user from Supabase access token.
    The frontend authenticates via Supabase Auth and sends the access_token
    as a Bearer token. We verify it using Supabase's get_user().
    """
    token = credentials.credentials

    try:
        user_response = supabase.auth.get_user(token)
        supabase_user = user_response.user

        if supabase_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract user metadata
        metadata = supabase_user.user_metadata or {}

        return {
            "supabase_id": supabase_user.id,
            "email": supabase_user.email,
            "full_name": metadata.get("full_name", ""),
            "user_name": metadata.get("user_name", ""),
            "is_admin": metadata.get("is_admin", False),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[dict]:
    """Optional dependency - returns None if no token provided"""
    if credentials is None:
        return None

    try:
        return get_current_user(credentials)
    except HTTPException:
        return None

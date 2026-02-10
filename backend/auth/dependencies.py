"""
Divya Vaani AI — FastAPI Auth Dependencies
Inject current user into route handlers.
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import decode_token
from db.database import get_db
from db import crud
from db.models import User

# Bearer token scheme (auto_error=False so unauthenticated requests pass through)
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Dependency: returns the current authenticated user or None.
    Use this for routes that work for both anonymous and authenticated users.
    """
    if credentials is None:
        return None

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = await crud.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        return None

    return user


async def require_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    """
    Dependency: requires an authenticated user.
    Returns 401 if not authenticated.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

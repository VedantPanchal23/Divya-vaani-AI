"""
Auth routes — register, login, refresh, profile.
"""
import logging
import re
from pydantic import BaseModel, field_validator
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db import crud
from auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from auth.dependencies import require_user
from db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# ── Request / Response Schemas ──

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        if len(v) > 255:
            raise ValueError("Email too long (max 255)")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        if len(v) > 128:
            raise ValueError("Password too long (max 128)")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 100:
            raise ValueError("Display name too long (max 100)")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    display_name: str

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Display name cannot be empty")
        if len(v) > 100:
            raise ValueError("Display name too long (max 100)")
        return v


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None
    created_at: str


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name or "",
        "created_at": user.created_at.isoformat() if user.created_at else "",
    }


# ── Endpoints ──

@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user account."""
    existing = await crud.get_user_by_email(db, req.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    hashed = hash_password(req.password)
    user = await crud.create_user(db, req.email, hashed, req.display_name or None)

    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    logger.info(f"New user registered: {user.email}")
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_dict(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Log in with email and password."""
    user = await crud.get_user_by_email(db, req.email.strip().lower())
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_dict(user),
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Get a new access token using a refresh token."""
    payload = decode_token(req.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    user = await crud.get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )

    access = create_access_token(user.id, user.email)
    refresh = create_refresh_token(user.id)

    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_dict(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_profile(user: User = Depends(require_user)):
    """Get current user profile."""
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.put("/me", response_model=UserResponse)
async def update_profile(
    req: UpdateProfileRequest,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Update display name."""
    updated = await crud.update_user(db, user.id, {"display_name": req.display_name})
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=updated.id,
        email=updated.email,
        display_name=updated.display_name,
        created_at=updated.created_at.isoformat() if updated.created_at else "",
    )

"""Shared helpers used across API sub-routers."""
import secrets
import logging
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, Header

from config import settings
from rate_limiter import limiter  # noqa: F401  — re-exported for sub-routers

logger = logging.getLogger(__name__)


def _safe_path(base_dir: Path, filename: str) -> Path:
    """Resolve a path and ensure it stays within base_dir (prevents path traversal)."""
    resolved = (base_dir / filename).resolve()
    base_resolved = base_dir.resolve()
    if not resolved.is_relative_to(base_resolved):
        raise HTTPException(400, "Invalid filename")
    return resolved


def _verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """Dependency to verify admin API key for protected endpoints."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(403, "Admin access disabled: ADMIN_API_KEY not configured on server.")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(403, "Invalid or missing admin API key. Set X-Admin-Key header.")


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

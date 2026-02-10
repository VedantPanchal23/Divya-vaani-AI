"""
User routes — favorites, chat history (DB-backed, requires auth).
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db import crud
from auth.dependencies import require_user
from db.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["user"])


# ══════════════════════
#  FAVORITES
# ══════════════════════

@router.get("/favorites")
async def list_favorites(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of video IDs the user has favorited."""
    video_ids = await crud.get_user_favorites(db, user.id)
    return {"favorites": video_ids}


@router.post("/favorites/{video_id}")
async def add_favorite(
    video_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a video to favorites."""
    # Verify video exists in DB
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(404, "Video not found")

    fav = await crud.add_favorite(db, user.id, video_id)
    return {"status": "added", "video_id": video_id}


@router.delete("/favorites/{video_id}")
async def remove_favorite(
    video_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a video from favorites."""
    removed = await crud.remove_favorite(db, user.id, video_id)
    if not removed:
        raise HTTPException(404, "Favorite not found")
    return {"status": "removed", "video_id": video_id}


# ══════════════════════
#  CHAT HISTORY
# ══════════════════════

@router.get("/chat-history")
async def list_chat_videos(
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of videos the user has chatted with."""
    videos = await crud.get_user_chat_videos(db, user.id)
    return {"videos": videos}


@router.get("/chat-history/{video_id}")
async def get_chat_history(
    video_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Get chat history for a specific video."""
    messages = await crud.get_chat_history(db, user.id, video_id, limit=100)
    return {
        "video_id": video_id,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "source_type": msg.source_type,
                "source_reference": msg.source_reference,
                "audio_url": msg.audio_url,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
            for msg in messages
        ],
    }


@router.delete("/chat-history/{video_id}")
async def clear_chat_history(
    video_id: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear chat history for a specific video."""
    count = await crud.clear_chat_history(db, user.id, video_id)
    return {"status": "cleared", "video_id": video_id, "deleted_count": count}

"""
Divya Vaani AI — Database CRUD Operations
Async functions for users, videos, chat messages, and favorites.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, Video, ChatMessage, Favorite

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#  VIDEO SERIALIZATION HELPERS
# ══════════════════════════════════════════════

def video_to_card(vid: Video) -> Dict[str, Any]:
    """Serialize a Video ORM object to a card dict (for listing)."""
    return {
        "id": vid.id,
        "title": vid.title,
        "title_hi": vid.title_hi or vid.title,
        "description": vid.description or "",
        "description_hi": vid.description_hi or "",
        "thumbnail": vid.thumbnail or "",
        "duration": vid.duration or 0,
        "category": vid.category or "pravachan",
        "speaker": vid.speaker or "Maharaj Ji",
        "tags": vid.tags or [],
        "created_at": vid.created_at.isoformat() if vid.created_at else "",
    }


def video_to_detail(vid: Video, language: str = "hi") -> Dict[str, Any]:
    """Serialize a Video ORM object to a full detail dict."""
    return {
        "id": vid.id,
        "title": vid.title if language == "en" else (vid.title_hi or vid.title),
        "title_hi": vid.title_hi or vid.title,
        "title_en": vid.title,
        "description": vid.description if language == "en" else (vid.description_hi or vid.description or ""),
        "thumbnail": vid.thumbnail or "",
        "video_url": vid.video_url or "",
        "duration": vid.duration or 0,
        "category": vid.category or "pravachan",
        "speaker": vid.speaker or "Maharaj Ji",
        "tags": vid.tags or [],
        # Full content
        "transcript": vid.transcript or "",
        "transcript_chunks": vid.transcript_chunks or [],
        "summary": (vid.summary_en if language == "en" else vid.summary_hi) or "",
        "summary_hi": vid.summary_hi or "",
        "summary_en": vid.summary_en or "",
        "explanation": (vid.explanation_en if language == "en" else vid.explanation_hi) or "",
        "explanation_hi": vid.explanation_hi or "",
        "explanation_en": vid.explanation_en or "",
        # Themes
        "main_topic": vid.main_topic or "",
        "main_topic_en": vid.main_topic_en or "",
        "themes": vid.themes or [],
        "themes_en": vid.themes_en or [],
        "key_teachings": vid.key_teachings or [],
        # Audio
        "summary_audio": (vid.summary_audio_en if language == "en" else vid.summary_audio_hi) or "",
        "summary_audio_hi": vid.summary_audio_hi or "",
        "summary_audio_en": vid.summary_audio_en or "",
        "explanation_audio": (vid.explanation_audio_en if language == "en" else vid.explanation_audio_hi) or "",
        "explanation_audio_hi": vid.explanation_audio_hi or "",
        "explanation_audio_en": vid.explanation_audio_en or "",
        "created_at": vid.created_at.isoformat() if vid.created_at else "",
        "status": "complete",
    }


# ══════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str, password_hash: str, display_name: str = None) -> User:
    user = User(email=email, password_hash=password_hash, display_name=display_name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user_id: str, updates: Dict[str, Any]) -> Optional[User]:
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    for key, value in updates.items():
        if hasattr(user, key) and key not in ("id", "email", "password_hash", "created_at"):
            setattr(user, key, value)
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


# ══════════════════════════════════════════════
#  VIDEOS
# ══════════════════════════════════════════════

async def get_all_videos_db(db: AsyncSession) -> List[Video]:
    result = await db.execute(select(Video).order_by(Video.created_at.desc()))
    return list(result.scalars().all())


async def get_video_by_id(db: AsyncSession, video_id: str) -> Optional[Video]:
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one_or_none()


async def upsert_video(db: AsyncSession, video_data: Dict[str, Any]) -> Video:
    """Insert or update a video record."""
    video_id = video_data.get("id")

    # Convert ISO datetime strings to Python datetime objects
    for dt_field in ("created_at", "updated_at"):
        val = video_data.get(dt_field)
        if isinstance(val, str):
            try:
                video_data[dt_field] = datetime.fromisoformat(val)
            except (ValueError, TypeError):
                video_data.pop(dt_field, None)

    # Strip unknown keys that aren't Video columns
    valid_cols = {c.key for c in Video.__table__.columns}
    video_data = {k: v for k, v in video_data.items() if k in valid_cols}

    existing = await get_video_by_id(db, video_id) if video_id else None

    if existing:
        for key, value in video_data.items():
            if hasattr(existing, key) and key != "id":
                setattr(existing, key, value)
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    video = Video(**video_data)
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video


async def delete_video_db(db: AsyncSession, video_id: str) -> bool:
    video = await get_video_by_id(db, video_id)
    if not video:
        return False
    await db.delete(video)
    await db.commit()
    return True


async def update_video_fields(db: AsyncSession, video_id: str, updates: Dict[str, Any]) -> bool:
    video = await get_video_by_id(db, video_id)
    if not video:
        return False
    for key, value in updates.items():
        if hasattr(video, key) and key != "id":
            setattr(video, key, value)
    video.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return True


# ══════════════════════════════════════════════
#  CHAT MESSAGES
# ══════════════════════════════════════════════

async def save_chat_message(
    db: AsyncSession,
    user_id: str,
    video_id: str,
    role: str,
    content: str,
    source_type: str = None,
    source_reference: str = None,
    audio_url: str = None,
) -> ChatMessage:
    msg = ChatMessage(
        user_id=user_id,
        video_id=video_id,
        role=role,
        content=content,
        source_type=source_type,
        source_reference=source_reference,
        audio_url=audio_url,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_chat_history(
    db: AsyncSession, user_id: str, video_id: str, limit: int = 50
) -> List[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.video_id == video_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_user_chat_videos(db: AsyncSession, user_id: str) -> List[Dict[str, Any]]:
    """Get list of videos a user has chatted with, with last message timestamp."""
    result = await db.execute(
        select(
            ChatMessage.video_id,
            func.max(ChatMessage.created_at).label("last_message"),
            func.count(ChatMessage.id).label("message_count"),
        )
        .where(ChatMessage.user_id == user_id)
        .group_by(ChatMessage.video_id)
        .order_by(func.max(ChatMessage.created_at).desc())
    )
    rows = result.all()
    return [
        {"video_id": r.video_id, "last_message": r.last_message.isoformat(), "message_count": r.message_count}
        for r in rows
    ]


async def clear_chat_history(db: AsyncSession, user_id: str, video_id: str) -> int:
    result = await db.execute(
        delete(ChatMessage).where(
            ChatMessage.user_id == user_id, ChatMessage.video_id == video_id
        )
    )
    await db.commit()
    return result.rowcount


# ══════════════════════════════════════════════
#  FAVORITES
# ══════════════════════════════════════════════

async def add_favorite(db: AsyncSession, user_id: str, video_id: str) -> Favorite:
    # Check if already exists
    result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.video_id == video_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    fav = Favorite(user_id=user_id, video_id=video_id)
    db.add(fav)
    await db.commit()
    await db.refresh(fav)
    return fav


async def remove_favorite(db: AsyncSession, user_id: str, video_id: str) -> bool:
    result = await db.execute(
        delete(Favorite).where(Favorite.user_id == user_id, Favorite.video_id == video_id)
    )
    await db.commit()
    return result.rowcount > 0


async def get_user_favorites(db: AsyncSession, user_id: str) -> List[str]:
    """Return list of video_ids the user has favorited."""
    result = await db.execute(
        select(Favorite.video_id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
    )
    return [r[0] for r in result.all()]


async def is_favorited(db: AsyncSession, user_id: str, video_id: str) -> bool:
    result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.video_id == video_id)
    )
    return result.scalar_one_or_none() is not None


async def get_video_favorite_count(db: AsyncSession, video_id: str) -> int:
    result = await db.execute(
        select(func.count(Favorite.id)).where(Favorite.video_id == video_id)
    )
    return result.scalar() or 0

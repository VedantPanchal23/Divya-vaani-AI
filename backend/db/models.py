"""
Divya Vaani AI — SQLAlchemy ORM Models
Tables: users, videos, chat_messages, favorites
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, JSON
)
from sqlalchemy.orm import relationship

from db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # Relationships
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


# ──────────────────────────────────────────────
# Videos (mirrors videos_content.json → DB)
# ──────────────────────────────────────────────
class Video(Base):
    __tablename__ = "videos"

    id = Column(String(36), primary_key=True)
    title = Column(String(500), nullable=False)
    title_hi = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    description_hi = Column(Text, nullable=True)
    thumbnail = Column(String(500), nullable=True)
    video_url = Column(String(500), nullable=True)
    duration = Column(Float, default=0.0)
    category = Column(String(100), default="pravachan")
    speaker = Column(String(200), default="Maharaj Ji")
    tags = Column(JSON, default=list)  # stored as JSON array

    # Full content
    transcript = Column(Text, nullable=True)
    transcript_chunks = Column(JSON, default=list)  # [{id, text, start_time, end_time}]
    summary_hi = Column(Text, nullable=True)
    summary_en = Column(Text, nullable=True)
    explanation_hi = Column(Text, nullable=True)
    explanation_en = Column(Text, nullable=True)

    # Themes
    main_topic = Column(String(500), default="")
    main_topic_en = Column(String(500), default="")
    themes = Column(JSON, default=list)
    themes_en = Column(JSON, default=list)
    key_teachings = Column(JSON, default=list)

    # Audio URLs
    summary_audio_hi = Column(String(500), nullable=True)
    summary_audio_en = Column(String(500), nullable=True)
    explanation_audio_hi = Column(String(500), nullable=True)
    explanation_audio_en = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


# ──────────────────────────────────────────────
# Chat Messages (per-user, per-video history)
# ──────────────────────────────────────────────
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=True)
    source_reference = Column(String(500), nullable=True)
    audio_url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="chat_messages")

    __table_args__ = (
        Index("ix_chat_user_video", "user_id", "video_id"),
    )


# ──────────────────────────────────────────────
# Favorites (user ♥ video)
# ──────────────────────────────────────────────
class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    video_id = Column(String(36), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_user_video_favorite"),
        Index("ix_fav_user", "user_id"),
    )

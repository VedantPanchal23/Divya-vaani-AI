"""
Divya Vaani AI — Async Database Engine
Supports PostgreSQL (production) and SQLite (development fallback).
"""
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from config import get_database_url

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass


# Lazy engine / session factory (initialised on first call)
_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        is_sqlite = url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {"timeout": 10}
        _engine = create_async_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            pool_timeout=10,
            connect_args=connect_args,
        )
        db_type = "SQLite" if is_sqlite else "PostgreSQL"
        logger.info(f"Database engine created ({db_type})")
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables (safe to call multiple times)."""
    engine = _get_engine()
    async with engine.begin() as conn:
        # Import models so Base.metadata knows about them
        from db import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified")


async def close_db():
    """Dispose the engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine disposed")

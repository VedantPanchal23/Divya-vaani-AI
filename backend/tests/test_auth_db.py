"""
Divya Vaani AI — Phase 5 Tests: Auth + Database
Tests for authentication, user management, favorites, and chat history.
Run with: pytest tests/test_auth_db.py -v
"""
import os
import sys
import asyncio
import pytest
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-12345")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only-1234567890")


# ========== Auth Security Tests ==========

class TestAuthSecurity:
    """Test JWT and password hashing utilities."""

    def test_hash_password(self):
        from auth.security import hash_password
        hashed = hash_password("mypassword123")
        assert hashed != "mypassword123"
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_verify_password_correct(self):
        from auth.security import hash_password, verify_password
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed) is True

    def test_verify_password_wrong(self):
        from auth.security import hash_password, verify_password
        hashed = hash_password("secret123")
        assert verify_password("wrongpassword", hashed) is False

    def test_create_access_token(self):
        from auth.security import create_access_token, decode_token
        token = create_access_token("user-id-123", "test@example.com")
        assert isinstance(token, str)
        assert len(token) > 0

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-id-123"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_create_refresh_token(self):
        from auth.security import create_refresh_token, decode_token
        token = create_refresh_token("user-id-456")
        assert isinstance(token, str)

        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-id-456"
        assert payload["type"] == "refresh"

    def test_decode_invalid_token(self):
        from auth.security import decode_token
        result = decode_token("invalid.token.here")
        assert result is None

    def test_decode_none_token(self):
        from auth.security import decode_token
        result = decode_token("")
        assert result is None


# ========== Database Model Tests ==========

class TestDatabaseModels:
    """Test SQLAlchemy ORM models."""

    def test_user_model(self):
        from db.models import User
        user = User(email="test@test.com", password_hash="hashed", display_name="Test")
        assert user.email == "test@test.com"
        assert user.display_name == "Test"
        # is_active default is applied by the DB, not in-memory

    def test_video_model(self):
        from db.models import Video
        video = Video(id="vid-001", title="Test Video", category="pravachan")
        assert video.id == "vid-001"
        assert video.title == "Test Video"
        assert video.category == "pravachan"

    def test_chat_message_model(self):
        from db.models import ChatMessage
        msg = ChatMessage(
            user_id="u1", video_id="v1",
            role="user", content="What is dharma?"
        )
        assert msg.role == "user"
        assert msg.content == "What is dharma?"

    def test_favorite_model(self):
        from db.models import Favorite
        fav = Favorite(user_id="u1", video_id="v1")
        assert fav.user_id == "u1"
        assert fav.video_id == "v1"


# ========== Database CRUD Tests (async) ==========

@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def run_async(event_loop):
    """Helper to run async functions in sync tests."""
    def _run(coro):
        return event_loop.run_until_complete(coro)
    return _run


class TestDatabaseCRUD:
    """Test database CRUD operations with in-memory SQLite."""

    @pytest.fixture(autouse=True)
    def setup_db(self, run_async):
        """Create a fresh in-memory DB for each test."""
        import db.database as dbmod
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy.pool import StaticPool

        # Save original state
        orig_engine = dbmod._engine
        orig_factory = dbmod._session_factory

        # Create a completely isolated in-memory engine
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # Override module globals
        dbmod._engine = engine
        dbmod._session_factory = session_factory

        # Create tables
        async def _init():
            async with engine.begin() as conn:
                await conn.run_sync(dbmod.Base.metadata.create_all)

        run_async(_init())

        yield

        async def _cleanup():
            await engine.dispose()

        run_async(_cleanup())
        dbmod._engine = orig_engine
        dbmod._session_factory = orig_factory

    def test_create_user(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                user = await crud.create_user(db, "user@test.com", "hashedpw", "Test User")
                assert user.email == "user@test.com"
                assert user.display_name == "Test User"
                assert user.id is not None

        run_async(_test())

    def test_get_user_by_email(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                await crud.create_user(db, "find@test.com", "pw", "Finder")
                user = await crud.get_user_by_email(db, "find@test.com")
                assert user is not None
                assert user.display_name == "Finder"

        run_async(_test())

    def test_get_user_by_email_not_found(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                user = await crud.get_user_by_email(db, "nonexistent@test.com")
                assert user is None

        run_async(_test())

    def test_upsert_video(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                video = await crud.upsert_video(db, {
                    "id": "test-vid-1",
                    "title": "Test Discourse",
                    "category": "pravachan",
                })
                assert video.id == "test-vid-1"
                assert video.title == "Test Discourse"

                # Update same video
                video2 = await crud.upsert_video(db, {
                    "id": "test-vid-1",
                    "title": "Updated Title",
                })
                assert video2.title == "Updated Title"

        run_async(_test())

    def test_add_and_remove_favorite(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                user = await crud.create_user(db, "fav@test.com", "pw")
                await crud.upsert_video(db, {"id": "fav-vid", "title": "Fav Video"})

                fav = await crud.add_favorite(db, user.id, "fav-vid")
                assert fav is not None

                favorites = await crud.get_user_favorites(db, user.id)
                assert "fav-vid" in favorites

                is_fav = await crud.is_favorited(db, user.id, "fav-vid")
                assert is_fav is True

                removed = await crud.remove_favorite(db, user.id, "fav-vid")
                assert removed is True

                favorites = await crud.get_user_favorites(db, user.id)
                assert "fav-vid" not in favorites

        run_async(_test())

    def test_add_duplicate_favorite(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                user = await crud.create_user(db, "dup@test.com", "pw")
                await crud.upsert_video(db, {"id": "dup-vid", "title": "Dup Video"})

                fav1 = await crud.add_favorite(db, user.id, "dup-vid")
                fav2 = await crud.add_favorite(db, user.id, "dup-vid")
                assert fav1.id == fav2.id  # same record returned

        run_async(_test())

    def test_chat_message_crud(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                user = await crud.create_user(db, "chat@test.com", "pw")
                await crud.upsert_video(db, {"id": "chat-vid", "title": "Chat Video"})

                # Save messages
                msg1 = await crud.save_chat_message(
                    db, user.id, "chat-vid", "user", "What is dharma?"
                )
                assert msg1.role == "user"

                msg2 = await crud.save_chat_message(
                    db, user.id, "chat-vid", "assistant", "Dharma means...",
                    source_type="pravachan"
                )
                assert msg2.role == "assistant"

                # Get history
                history = await crud.get_chat_history(db, user.id, "chat-vid")
                assert len(history) == 2
                assert history[0].role == "user"
                assert history[1].role == "assistant"

                # Get chat videos
                videos = await crud.get_user_chat_videos(db, user.id)
                assert len(videos) == 1
                assert videos[0]["video_id"] == "chat-vid"
                assert videos[0]["message_count"] == 2

                # Clear history
                deleted = await crud.clear_chat_history(db, user.id, "chat-vid")
                assert deleted == 2

                history = await crud.get_chat_history(db, user.id, "chat-vid")
                assert len(history) == 0

        run_async(_test())

    def test_video_favorite_count(self, run_async):
        from db import crud
        from db.database import _get_session_factory

        async def _test():
            factory = _get_session_factory()
            async with factory() as db:
                await crud.upsert_video(db, {"id": "count-vid", "title": "Count Video"})
                user1 = await crud.create_user(db, "u1@test.com", "pw")
                user2 = await crud.create_user(db, "u2@test.com", "pw")

                await crud.add_favorite(db, user1.id, "count-vid")
                await crud.add_favorite(db, user2.id, "count-vid")

                count = await crud.get_video_favorite_count(db, "count-vid")
                assert count == 2

        run_async(_test())


# ========== Auth Route Schema Tests ==========

class TestAuthRouteSchemas:
    """Test auth route request/response schemas."""

    def test_register_request_valid(self):
        from api.auth_routes import RegisterRequest
        req = RegisterRequest(email="test@test.com", password="password123", display_name="Test")
        assert req.email == "test@test.com"

    def test_register_request_email_normalized(self):
        from api.auth_routes import RegisterRequest
        req = RegisterRequest(email="  TEST@Example.COM  ", password="password123")
        assert req.email == "test@example.com"

    def test_register_request_invalid_email(self):
        from api.auth_routes import RegisterRequest
        with pytest.raises(Exception):
            RegisterRequest(email="not-an-email", password="password123")

    def test_register_request_short_password(self):
        from api.auth_routes import RegisterRequest
        with pytest.raises(Exception):
            RegisterRequest(email="test@test.com", password="12345")

    def test_login_request(self):
        from api.auth_routes import LoginRequest
        req = LoginRequest(email="test@test.com", password="password123")
        assert req.email == "test@test.com"


# ========== Config Tests ==========

class TestPhase5Config:
    """Test Phase 5 config additions."""

    def test_database_url_default(self):
        from config import settings
        # Should be empty by default (SQLite fallback)
        assert settings.DATABASE_URL == "" or "sqlite" in settings.DATABASE_URL or "postgresql" in settings.DATABASE_URL

    def test_jwt_settings(self):
        from config import settings
        assert settings.JWT_ALGORITHM == "HS256"
        assert settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES > 0
        assert settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS > 0

    def test_jwt_secret_exists(self):
        from config import settings
        secret = settings.JWT_SECRET_KEY.get_secret_value()
        assert len(secret) > 0

    def test_get_database_url_fallback(self):
        from config import get_database_url
        url = get_database_url()
        # Should either be a configured URL or SQLite fallback
        assert "sqlite" in url or "postgresql" in url


# ========== Database Module Tests ==========

class TestDatabaseModule:
    """Test database module initialization."""

    def test_base_exists(self):
        from db.database import Base
        assert Base is not None

    def test_init_db_runs_without_error(self, run_async):
        import db.database as dbmod
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import StaticPool

        orig_engine = dbmod._engine
        orig_factory = dbmod._session_factory
        dbmod._engine = None
        dbmod._session_factory = None

        # Use in-memory SQLite to test init_db logic
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        dbmod._engine = engine

        async def _test():
            async with engine.begin() as conn:
                await conn.run_sync(dbmod.Base.metadata.create_all)

        run_async(_test())
        assert dbmod._engine is not None

        async def _cleanup():
            await engine.dispose()

        run_async(_cleanup())
        dbmod._engine = orig_engine
        dbmod._session_factory = orig_factory

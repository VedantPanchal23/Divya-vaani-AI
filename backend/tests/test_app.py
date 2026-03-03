"""
Divya Vaani AI — Test Suite
Tests for config, helpers, schema, and API routes.
Run with: pytest tests/ -v
"""
import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Add backend to path
BACKEND_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(BACKEND_DIR))

# Set required env vars before importing app modules
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key-12345")


# ========== Config Tests ==========

class TestConfig:
    """Test config.py settings."""

    def test_settings_load(self):
        from config import settings
        assert settings.APP_NAME == "Divya Vaani AI"
        assert settings.PORT == 8000

    def test_settings_paths_exist(self):
        from config import settings
        assert settings.DATA_DIR.exists()
        assert isinstance(settings.UPLOAD_DIR, Path)
        assert isinstance(settings.TRANSCRIPT_DIR, Path)

    def test_settings_embedding_dim(self):
        from config import settings
        assert settings.EMBEDDING_DIM == 384

    def test_settings_rate_limits(self):
        from config import settings
        assert "minute" in settings.RATE_LIMIT_CHAT or "hour" in settings.RATE_LIMIT_CHAT
        assert "minute" in settings.RATE_LIMIT_TTS or "hour" in settings.RATE_LIMIT_TTS

    def test_max_upload_size(self):
        from config import settings
        assert settings.MAX_UPLOAD_SIZE_MB > 0
        assert settings.MAX_UPLOAD_SIZE_MB <= 2000  # sanity check


# ========== Schema Tests ==========

class TestSchema:
    """Test Pydantic schema models."""

    def test_source_type_enum(self):
        from data.schema import SourceType
        assert SourceType.PRAVACHAN == "pravachan"
        assert SourceType.GITA == "bhagavad_gita"
        assert SourceType.NOT_FOUND == "not_found"

    def test_transcript_chunk(self):
        from data.schema import TranscriptChunk
        chunk = TranscriptChunk(id="c1", text="test", start_time=0.0, end_time=5.0)
        assert chunk.id == "c1"
        assert chunk.end_time == 5.0

    def test_upload_response(self):
        from data.schema import UploadResponse
        resp = UploadResponse(
            file_id="abc123",
            filename="test.mp3",
            status="processing",
            message="ok"
        )
        assert resp.file_id == "abc123"

    def test_chat_request(self):
        from data.schema import ChatRequest
        req = ChatRequest(question="What is dharma?", language="en")
        assert req.question == "What is dharma?"

    def test_tts_request(self):
        from data.schema import TTSRequest
        req = TTSRequest(text="Hello", language="en")
        assert req.text == "Hello"

    def test_chat_response(self):
        from data.schema import ChatResponse, SourceType
        resp = ChatResponse(
            answer="Test answer",
            source_type=SourceType.GITA,
            source_reference="Ch 1, V 1",
            audio_url=""
        )
        assert resp.source_type == SourceType.GITA


# ========== Helpers Tests ==========

class TestHelpers:
    """Test API helper functions."""

    def test_safe_path_valid(self):
        from api._helpers import _safe_path
        base = Path(__file__).parent
        result = _safe_path(base, "testfile.txt")
        assert result.parent == base.resolve()

    def test_safe_path_traversal_blocked(self):
        from api._helpers import _safe_path
        from fastapi import HTTPException
        base = Path(__file__).parent
        with pytest.raises(HTTPException) as exc_info:
            _safe_path(base, "../../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_format_time(self):
        from api._helpers import _format_time
        assert _format_time(0) == "00:00"
        assert _format_time(65) == "01:05"
        assert _format_time(3661) == "61:01"

    def test_verify_admin_key_missing(self):
        from api._helpers import _verify_admin_key
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_admin_key(x_admin_key=None)
        assert exc_info.value.status_code == 403

    def test_verify_admin_key_wrong(self):
        from api._helpers import _verify_admin_key
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_admin_key(x_admin_key="wrong-key")
        assert exc_info.value.status_code == 403

    def test_verify_admin_key_correct(self):
        from api._helpers import _verify_admin_key
        # Should not raise
        _verify_admin_key(x_admin_key="test-admin-key-12345")


# ========== Videos Content Tests ==========

class TestVideosContent:
    """Test data/videos_content.py CRUD operations."""

    def test_get_all_videos(self):
        from data.videos_content import get_all_videos
        videos = get_all_videos()
        assert isinstance(videos, list)

    def test_get_video_detail_not_found(self):
        from data.videos_content import get_video_detail
        result = get_video_detail("nonexistent-id-99999", "hi")
        assert result is None


# ========== Chat Routes Unit Tests ==========

class TestChatHelpers:
    """Test chat route helper functions."""

    def test_expand_question_english(self):
        from api.chat_routes import _expand_question_for_search
        result = _expand_question_for_search("I am feeling sad today")
        assert "दुख" in result  # Should expand with Hindi keywords

    def test_expand_question_hindi(self):
        from api.chat_routes import _expand_question_for_search
        result = _expand_question_for_search("मैं बहुत परेशान हूँ")
        assert "समाधान" in result

    def test_expand_question_no_match(self):
        from api.chat_routes import _expand_question_for_search
        q = "What is the weather today?"
        result = _expand_question_for_search(q)
        assert result == q  # No expansion when no keyword matches


# ========== Upload Routes Tests ==========

class TestUploadHelpers:
    """Test upload route utilities."""

    def test_cleanup_old_status(self):
        import time
        from api.upload_routes import _status, _cleanup_old_status, STATUS_TTL_SECONDS
        # Add an old completed entry
        _status["test-old"] = {
            "status": "complete",
            "_timestamp": time.time() - STATUS_TTL_SECONDS - 100
        }
        _cleanup_old_status()
        assert "test-old" not in _status

    def test_status_store_bounded(self):
        import time
        from api.upload_routes import _status, _cleanup_old_status, MAX_STATUS_ENTRIES
        # This is just a sanity check on constants
        assert MAX_STATUS_ENTRIES == 100


# ========== Integration Test with FastAPI TestClient ==========

class TestAPIEndpoints:
    """Integration tests using FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Set up test client with lifespan so DB tables are created."""
        from fastapi.testclient import TestClient
        from run import app
        with TestClient(app) as client:
            self.client = client
            yield

    def test_health_check(self):
        response = self.client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_get_videos(self):
        response = self.client.get("/api/videos")
        assert response.status_code == 200
        data = response.json()
        assert "videos" in data
        assert "total" in data

    def test_get_video_not_found(self):
        response = self.client.get("/api/videos/nonexistent-id")
        assert response.status_code == 404

    def test_chat_empty_question(self):
        response = self.client.post("/api/chat", json={
            "question": "",
            "language": "hi"
        })
        assert response.status_code == 400

    def test_chat_too_long_question(self):
        response = self.client.post("/api/chat", json={
            "question": "x" * 1500,
            "language": "hi"
        })
        assert response.status_code == 400

    def test_chat_video_scope_skips_gita_fallback(self):
        """When transcript_id is provided, failed transcript retrieval should not auto-fallback to Gita."""
        from data.schema import GitaVerse

        fake_gita_results = [{
            "verse": GitaVerse(chapter=2, verse=47, hindi="x", english="y"),
            "score": 0.95,
        }]

        with patch(
            "api.chat_routes.rag_engine.search_transcripts_hybrid",
            side_effect=[[], []],
        ) as mock_hybrid, patch(
            "api.chat_routes.rag_engine.search_gita",
            return_value=fake_gita_results,
        ) as mock_search_gita, patch(
            "api.chat_routes.llm_engine.generate_search_queries",
            new=AsyncMock(return_value=[]),
        ), patch(
            "api.chat_routes.llm_engine.generate_not_found",
            new=AsyncMock(return_value="not-found-from-transcript"),
        ), patch(
            "api.chat_routes.llm_engine.is_english_text",
            return_value=False,
        ), patch(
            "api.chat_routes.llm_engine._is_prompt_injection",
            return_value=False,
        ):
            response = self.client.post("/api/chat", json={
                "question": "मन को कैसे शांत करें?",
                "transcript_id": "video-123",
                "language": "hi",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["source_type"] == "not_found"
        # After fix: video-scoped not-found returns a user-friendly Hindi message
        assert "इस प्रवचन" in data["answer"] or data["answer"] == "not-found-from-transcript"
        assert mock_hybrid.call_count == 2  # strict + relaxed retry
        assert mock_search_gita.call_count == 0  # no Gita fallback in video-scoped mode

    def test_chat_relaxed_transcript_retry_returns_pravachan(self):
        """If strict threshold misses and relaxed retry finds context, answer should come from pravachan."""
        from config import settings
        from data.schema import TranscriptChunk

        fake_chunk = TranscriptChunk(
            id="chunk-1",
            text="महाराज जी बताते हैं कि मन को साधना और नाम जप से स्थिर किया जा सकता है।",
            start_time=12.0,
            end_time=24.0,
        )
        fake_result = {
            "chunk": fake_chunk,
            "score": 0.82,
            "semantic_score": 0.82,
            "keyword_score": 0.10,
            "rrf_score": 0.01,
        }

        mock_generate_answer = AsyncMock(return_value="transcript-grounded-answer")

        with patch(
            "api.chat_routes.rag_engine.search_transcripts_hybrid",
            side_effect=[[], [fake_result]],
        ) as mock_hybrid, patch(
            "api.chat_routes.llm_engine.generate_search_queries",
            new=AsyncMock(return_value=[]),
        ), patch(
            "api.chat_routes.llm_engine.generate_answer",
            new=mock_generate_answer,
        ), patch(
            "api.chat_routes.llm_engine.generate_not_found",
            new=AsyncMock(return_value="not-found"),
        ), patch(
            "api.chat_routes.llm_engine.is_english_text",
            return_value=False,
        ), patch(
            "api.chat_routes.llm_engine._is_prompt_injection",
            return_value=False,
        ):
            response = self.client.post("/api/chat", json={
                "question": "मन को कैसे नियंत्रित करें?",
                "transcript_id": "video-123",
                "language": "hi",
            })

        assert response.status_code == 200
        data = response.json()
        assert data["source_type"] == "pravachan"
        assert data["answer"] == "transcript-grounded-answer"
        assert mock_hybrid.call_count == 2
        second_call_kwargs = mock_hybrid.call_args_list[1].kwargs
        assert "semantic_min_score" in second_call_kwargs
        assert second_call_kwargs["semantic_min_score"] < settings.SIMILARITY_THRESHOLD
        assert mock_generate_answer.await_count == 1

    def test_tts_empty_text(self):
        response = self.client.post("/api/tts", json={
            "text": "",
            "language": "hi"
        })
        assert response.status_code == 400

    def test_tts_too_long(self):
        response = self.client.post("/api/tts", json={
            "text": "x" * 3000,
            "language": "hi"
        })
        assert response.status_code == 400

    def test_upload_no_admin_key(self):
        """Upload requires admin key."""
        response = self.client.post("/api/upload", files={
            "file": ("test.mp3", b"fake audio data", "audio/mpeg")
        })
        assert response.status_code == 403

    def test_upload_wrong_filetype(self):
        """Upload rejects unsupported types."""
        response = self.client.post(
            "/api/upload",
            files={"file": ("test.exe", b"data", "application/octet-stream")},
            headers={"X-Admin-Key": "test-admin-key-12345"}
        )
        assert response.status_code == 400

    def test_delete_video_no_admin_key(self):
        response = self.client.delete("/api/videos/some-id")
        assert response.status_code == 403

    def test_thumbnail_not_found(self):
        response = self.client.get("/api/thumbnail/nonexistent")
        assert response.status_code == 404

    def test_audio_invalid_filename(self):
        response = self.client.get("/api/audio/bad file!@#.mp3")
        assert response.status_code == 400

    def test_tts_status(self):
        response = self.client.get("/api/tts/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

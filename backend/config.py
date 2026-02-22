"""
Divya Vaani AI - Configuration
Simple, clean configuration using environment variables.
"""
import os
import secrets
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings

# Paths
BACKEND_DIR = Path(__file__).parent.absolute()

# Python package directory (schema.py, bhagavad_gita.json, etc.)
# This must NEVER be overwritten by a volume mount.
PACKAGE_DATA_DIR = BACKEND_DIR / "data"

# User storage directory (uploads, transcripts, audio, FAISS indexes)
# In production (Railway), set STORAGE_DIR env var and mount volume there.
_storage_dir = os.environ.get("STORAGE_DIR")
DATA_DIR = Path(_storage_dir) if _storage_dir else PACKAGE_DATA_DIR


class Settings(BaseSettings):
    """Application settings."""
    
    # App Info
    APP_NAME: str = "Divya Vaani AI"
    APP_VERSION: str = "3.1.0"
    DEBUG: bool = False
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Security
    ADMIN_API_KEY: str = ""  # REQUIRED for production - protects upload/admin endpoints
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"  # Comma-separated origins
    RATE_LIMIT_CHAT: str = "20/minute"  # Rate limit for chat endpoint
    RATE_LIMIT_TTS: str = "30/minute"   # Rate limit for TTS endpoint
    RATE_LIMIT_UPLOAD: str = "5/hour"   # Rate limit for upload endpoint
    MAX_UPLOAD_SIZE_MB: int = 500       # Max upload file size in MB
    
    # Database
    DATABASE_URL: str = ""  # PostgreSQL: postgresql+asyncpg://user:pass@host/db  (empty = SQLite fallback)
    
    # JWT Authentication
    JWT_SECRET_KEY: SecretStr = SecretStr("")  # Auto-generated if empty
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # Groq API (Transcription + Fast Q&A)
    GROQ_API_KEY: SecretStr = SecretStr("")
    
    # Gemini API (Summary + Explanation - better for long content)
    GEMINI_API_KEY: SecretStr = SecretStr("")
    
    # LLM Settings
    LLM_MODEL: str = "llama-3.3-70b-versatile"  # For summaries/explanations (quality)
    LLM_MODEL_FAST: str = "llama-3.3-70b-versatile"  # For Q&A — quality matters more than speed for spiritual guidance
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 3000  # Allow rich, detailed answers
    
    # TTS Settings (Optimized for Speed)
    TTS_MODE: str = "fast"         # "fast" (Edge TTS - low latency) or "custom" (future custom TTS model)
    TTS_SAMPLE_RATE: int = 22050   # Sample rate for TTS output
    TTS_CACHE_MAX_SIZE: int = 500  # Max number of TTS audio files to cache
    AUDIO_CLEANUP_HOURS: int = 24  # Delete audio files older than this
    
    # Paths (computed)
    @property
    def UPLOAD_DIR(self) -> Path:
        path = DATA_DIR / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def TRANSCRIPT_DIR(self) -> Path:
        path = DATA_DIR / "transcripts"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def TRANSCRIPTS_DIR(self) -> Path:
        # Alias for backward compatibility
        return self.TRANSCRIPT_DIR
    
    @property
    def DATA_DIR(self) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR
    
    @property
    def AUDIO_DIR(self) -> Path:
        path = DATA_DIR / "audio"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def GITA_PATH(self) -> Path:
        return PACKAGE_DATA_DIR / "bhagavad_gita.json"
    
    @property
    def INDEX_DIR(self) -> Path:
        path = DATA_DIR / "index"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # RAG Settings - Using E5 multilingual (best for retrieval)
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"  # Best for Hindi+English retrieval
    EMBEDDING_DIM: int = 384  # Dimension for this model
    TOP_K: int = 10  # Retrieve more chunks for better context
    SIMILARITY_THRESHOLD: float = 0.35  # Lowered: Hindi ASR transcripts often score 0.35-0.50
    GITA_EXPLICIT_THRESHOLD: float = 0.45  # Lower threshold for explicit Gita questions (broader results)
    GITA_FALLBACK_THRESHOLD: float = 0.60  # Higher threshold for fallback (prevents weak matches)
    HYBRID_SEARCH_ENABLED: bool = True  # Enable hybrid semantic+keyword search
    RELEVANCE_CHECK_ENABLED: bool = True  # LLM verifies context relevance before answering
    
    # Transcription Enhancement Settings
    PARALLEL_TRANSCRIPTION: bool = True  # Process chunks in parallel for speed
    MAX_PARALLEL_CHUNKS: int = 6  # Max concurrent API calls
    CHUNK_OVERLAP_SECONDS: int = 15  # Overlap between chunks to prevent cut-off words
    ENABLE_LLM_CORRECTION: bool = True  # Use Gemini to correct transcription errors
    LLM_CORRECTION_MODEL: str = "gemini-2.0-flash"  # Fast + accurate for correction
    
    class Config:
        env_file = BACKEND_DIR / ".env"
        extra = "ignore"


settings = Settings()

# === Startup Validation ===
import os as _os

# In production (not DEBUG), ADMIN_API_KEY must be set to protect admin endpoints
if not settings.DEBUG and not settings.ADMIN_API_KEY:
    _generated = secrets.token_urlsafe(32)
    settings.ADMIN_API_KEY = _generated
    import warnings
    warnings.warn(
        "\n" + "=" * 60 + "\n"
        "  WARNING: ADMIN_API_KEY was not set!\n"
        f"  Auto-generated key: {_generated}\n"
        "  Set ADMIN_API_KEY env var for production.\n"
        + "=" * 60,
        stacklevel=1
    )

if settings.CORS_ORIGINS == "*" and not settings.DEBUG:
    import warnings
    warnings.warn(
        "CORS_ORIGINS='*' in production — restrict to your frontend domain.",
        stacklevel=1
    )

# Auto-generate JWT secret if not provided
if not settings.JWT_SECRET_KEY.get_secret_value():
    _jwt_secret = secrets.token_urlsafe(64)
    settings.JWT_SECRET_KEY = SecretStr(_jwt_secret)
    if not settings.DEBUG:
        import warnings
        warnings.warn(
            "JWT_SECRET_KEY not set — auto-generated (tokens won't survive restarts). "
            "Set JWT_SECRET_KEY env var for production.",
            stacklevel=1
        )

# Compute async database URL
def get_database_url() -> str:
    """Return the async database URL, falling back to SQLite."""
    if settings.DATABASE_URL:
        url = settings.DATABASE_URL
        # Convert postgres:// to postgresql+asyncpg://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    # Fallback to SQLite
    db_path = DATA_DIR / "divyavaani.db"
    return f"sqlite+aiosqlite:///{db_path}"

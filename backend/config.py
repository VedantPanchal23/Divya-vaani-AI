"""
Divya Vaani AI - Configuration
Simple, clean configuration using environment variables.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Paths
BACKEND_DIR = Path(__file__).parent.absolute()
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    """Application settings."""
    
    # App Info
    APP_NAME: str = "Divya Vaani AI"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = True
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Groq API (Transcription + Fast Q&A)
    GROQ_API_KEY: str = ""
    
    # Gemini API (Summary + Explanation - better for long content)
    GEMINI_API_KEY: str = ""
    
    # LLM Settings
    LLM_MODEL: str = "llama-3.3-70b-versatile"  # For summaries/explanations (quality)
    LLM_MODEL_FAST: str = "llama-3.1-8b-instant"  # For Q&A (speed) - ~5x faster
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 2000
    
    # TTS Settings (Optimized for Speed)
    TTS_MODE: str = "clone"        # "fast" (Edge TTS - low latency) or "clone" (voice cloning)
    USE_VOICE_CLONING: bool = True  # Enable voice cloning (requires TTS library)
    VOICE_SAMPLE_PATH: str = ""    # Path to voice sample (auto-detected if empty)
    MAHARAJ_MODEL_PATH: str = ""   # Path to custom trained model (if any)
    REFERENCE_AUDIO_PATH: str = "" # Path to reference audio for cloning (10-30s recommended)
    REFERENCE_TRANSCRIPT_PATH: str = ""  # Optional: transcript of reference audio
    TTS_SAMPLE_RATE: int = 22050   # Sample rate for TTS output (XTTS requirement)
    TTS_MODEL: str = "XTTS"        # Model: "EdgeTTS" (fast), "XTTS" (voice cloning)
    
    # Paths (computed)
    @property
    def UPLOAD_DIR(self) -> Path:
        path = DATA_DIR / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def TRANSCRIPTS_DIR(self) -> Path:
        path = DATA_DIR / "transcripts"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def AUDIO_DIR(self) -> Path:
        path = DATA_DIR / "audio"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def GITA_PATH(self) -> Path:
        return DATA_DIR / "bhagavad_gita.json"
    
    @property
    def INDEX_DIR(self) -> Path:
        path = DATA_DIR / "index"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # RAG Settings - Using E5 multilingual (best for retrieval)
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-small"  # Best for Hindi+English retrieval
    EMBEDDING_DIM: int = 384  # Dimension for this model
    TOP_K: int = 10  # Retrieve more chunks for better context
    SIMILARITY_THRESHOLD: float = 0.3  # Lower threshold to allow more relevant spiritual guidance
    
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

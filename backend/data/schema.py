"""
Divya Vaani AI - Data Schema
Pydantic models for API requests/responses.
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel


class SourceType(str, Enum):
    """Source type for answers."""
    PRAVACHAN = "pravachan"
    GITA = "bhagavad_gita"
    NOT_FOUND = "not_found"


class TranscriptChunk(BaseModel):
    """A chunk of transcribed audio."""
    id: str
    text: str
    start_time: float
    end_time: float


class Transcript(BaseModel):
    """Complete transcript."""
    id: str
    filename: str
    title: str
    chunks: List[TranscriptChunk]
    duration: float
    created_at: datetime
    full_text: str = ""


class GitaVerse(BaseModel):
    """A Bhagavad Gita verse."""
    chapter: int
    verse: int
    sanskrit: str = ""
    hindi: str = ""
    english: str = ""


# ========== API Request/Response Models ==========

class UploadResponse(BaseModel):
    """Response after file upload."""
    file_id: str
    filename: str
    status: str
    message: str


class TranscriptResponse(BaseModel):
    """Response with transcript data."""
    id: str
    title: str
    filename: str
    duration: float
    status: str
    chunks: List[TranscriptChunk] = []
    full_text: str = ""
    summary: Optional[str] = None
    summary_audio: Optional[str] = None
    explanation: Optional[str] = None
    explanation_audio: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat/Q&A request."""
    question: str
    transcript_id: Optional[str] = None
    language: str = "hi"  # "hi" or "en"


class ChatResponse(BaseModel):
    """Chat/Q&A response."""
    answer: str
    source_type: SourceType
    source_reference: str = ""
    audio_url: Optional[str] = None


class TTSRequest(BaseModel):
    """Text-to-speech request."""
    text: str
    language: str = "hi"


class TTSResponse(BaseModel):
    """Text-to-speech response."""
    audio_url: str

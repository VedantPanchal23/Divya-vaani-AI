"""TTS & voice transcription routes."""
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Request

from config import settings
from data.schema import TTSRequest, TTSResponse
from core import transcriber, tts_engine
from ._helpers import _safe_path, limiter
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_TTS_TEXT_LENGTH = 2000


@router.post("/transcribe-voice")
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def transcribe_voice_input(request: Request, audio: UploadFile = File(...), language: str = None):
    """Transcribe voice input (for asking questions by voice)."""
    temp_path = settings.UPLOAD_DIR / f"voice_{uuid.uuid4()}.webm"
    try:
        file_size = 0
        max_voice_size = 10 * 1024 * 1024
        with open(temp_path, "wb") as f:
            while chunk := await audio.read(1024 * 64):
                file_size += len(chunk)
                if file_size > max_voice_size:
                    raise HTTPException(413, "Voice recording too large (max 10MB)")
                f.write(chunk)
        text = await transcriber.transcribe_voice(temp_path, language=language)
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Voice transcription failed: {e}")
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


@router.post("/tts", response_model=TTSResponse)
@limiter.limit(settings.RATE_LIMIT_TTS)
async def synthesize_speech(request: Request, tts_request: TTSRequest):
    """Convert text to speech. Rate limited."""
    if not tts_request.text or not tts_request.text.strip():
        raise HTTPException(400, "Text is required for TTS.")
    if len(tts_request.text) > MAX_TTS_TEXT_LENGTH:
        raise HTTPException(400, f"Text too long. Max {MAX_TTS_TEXT_LENGTH} characters.")
    audio_url = await tts_engine.generate_speech_async(
        tts_request.text, tts_request.language, tts_request.gender
    )
    if not audio_url:
        raise HTTPException(500, "TTS generation failed")
    return TTSResponse(audio_url=audio_url)


@router.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve audio files."""
    if not all(c.isalnum() or c in '-_.' for c in filename):
        raise HTTPException(400, "Invalid filename")
    path = _safe_path(settings.AUDIO_DIR, filename)
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/tts/status")
async def tts_status():
    """Get status of TTS system."""
    return {
        "mode": settings.TTS_MODE,
        "engines": ["gTTS", "Edge TTS"],
        "status": "active",
        "note": "Custom person-specific TTS model support coming in next version"
    }

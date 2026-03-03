"""Upload & Transcript routes."""
import uuid
import re
import time
import logging
import tempfile
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request, Depends

from config import settings
from data.schema import UploadResponse
from db.database import _get_session_factory
from db import crud
from core import transcriber, llm_engine, rag_engine, tts_engine
from ._helpers import _verify_admin_key, limiter

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory status store for processing jobs (bounded)
_status: Dict[str, dict] = {}
MAX_STATUS_ENTRIES = 100

# Max upload file size from config
MAX_UPLOAD_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Status TTL: 1 hour
STATUS_TTL_SECONDS = 3600


def _cleanup_old_status():
    """Remove completed/error status entries older than TTL and enforce max size."""
    now = time.time()
    to_delete = [
        k for k, v in _status.items()
        if v.get("status") in ("complete", "error")
        and now - v.get("_timestamp", now) > STATUS_TTL_SECONDS
    ]
    for k in to_delete:
        del _status[k]
    if len(_status) > MAX_STATUS_ENTRIES:
        completed = sorted(
            [(k, v) for k, v in _status.items() if v.get("status") in ("complete", "error")],
            key=lambda x: x[1].get("_timestamp", 0)
        )
        for k, _ in completed[:len(_status) - MAX_STATUS_ENTRIES]:
            del _status[k]


@router.post("/upload", response_model=UploadResponse, dependencies=[Depends(_verify_admin_key)])
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_file(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload audio/video for transcription. Returns immediately; processing in background."""
    allowed_types = [".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg", ".flac"]
    file_ext = Path(file.filename or "unknown").suffix.lower()

    if file_ext not in allowed_types:
        raise HTTPException(400, f"File type {file_ext} not supported. Use: {allowed_types}")

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(413, f"File too large. Max allowed: {settings.MAX_UPLOAD_SIZE_MB} MB")

    file_id = str(uuid.uuid4())[:12]
    file_path = settings.UPLOAD_DIR / f"{file_id}{file_ext}"

    try:
        file_size = 0
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_SIZE_BYTES:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"File too large ({file_size / (1024*1024):.1f} MB). "
                        f"Max allowed: {settings.MAX_UPLOAD_SIZE_MB} MB"
                    )
                f.write(chunk)
        logger.info(f"Uploaded: {file.filename} ({file_size / (1024*1024):.1f} MB)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {e}")

    _cleanup_old_status()

    _status[file_id] = {
        "status": "processing",
        "step": "transcribing",
        "progress": 0,
        "message": "Starting transcription...",
        "_timestamp": time.time()
    }

    background_tasks.add_task(_process_upload, file_id, file_path, file.filename)

    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        status="processing",
        message="Upload successful. Transcription started."
    )


# ========== YouTube URL Upload ==========

_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[\w&=]*&)?v=|shorts/)|youtu\.be/)([\w-]{11})"
)


class YouTubeUploadRequest(BaseModel):
    url: str
    title: Optional[str] = None


def _extract_video_id(url: str) -> str | None:
    """Extract the 11-char YouTube video ID from various URL formats."""
    m = _YOUTUBE_URL_RE.search(url)
    return m.group(1) if m else None


async def _download_youtube_audio(url: str, output_dir: Path) -> tuple[Path, dict]:
    """Download audio from YouTube URL using yt-dlp. Returns (file_path, info_dict)."""
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is not installed on the server. Cannot download YouTube videos.")

    output_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())[:12]
    output_template = str(output_dir / f"{file_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "http_chunk_size": 1048576,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    import asyncio
    loop = asyncio.get_running_loop()

    info = {}

    def _do_download():
        nonlocal info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        return info

    try:
        info = await loop.run_in_executor(None, _do_download)
    except Exception as e:
        raise RuntimeError(f"Failed to download YouTube video: {e}")

    # Find the downloaded mp3 file
    mp3_path = output_dir / f"{file_id}.mp3"
    if not mp3_path.exists():
        # Sometimes yt-dlp uses different naming — scan for the file
        candidates = list(output_dir.glob(f"{file_id}.*"))
        if candidates:
            mp3_path = candidates[0]
        else:
            raise RuntimeError("Download succeeded but audio file not found.")

    return mp3_path, info


@router.post("/upload/youtube", response_model=UploadResponse, dependencies=[Depends(_verify_admin_key)])
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_youtube(
    request: Request,
    body: YouTubeUploadRequest,
    background_tasks: BackgroundTasks,
):
    """Upload a YouTube video by URL. Downloads audio, then processes like a file upload."""
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "YouTube URL is required.")

    video_yt_id = _extract_video_id(url)
    if not video_yt_id:
        raise HTTPException(400, "Invalid YouTube URL. Accepted formats: youtube.com/watch?v=..., youtu.be/..., youtube.com/shorts/...")

    file_id = str(uuid.uuid4())[:12]

    _cleanup_old_status()
    _status[file_id] = {
        "status": "processing",
        "step": "downloading",
        "progress": 0,
        "message": f"Downloading audio from YouTube ({video_yt_id})...",
        "_timestamp": time.time(),
    }

    background_tasks.add_task(_process_youtube_upload, file_id, url, body.title)

    return UploadResponse(
        file_id=file_id,
        filename=f"youtube-{video_yt_id}",
        status="processing",
        message="YouTube download started. Processing will begin automatically.",
    )


async def _process_youtube_upload(file_id: str, url: str, custom_title: str | None):
    """Background task: download YouTube audio, then run standard processing pipeline."""
    try:
        _status[file_id]["step"] = "downloading"
        _status[file_id]["message"] = "Downloading audio from YouTube..."
        _status[file_id]["progress"] = 5

        mp3_path, info = await _download_youtube_audio(url, settings.UPLOAD_DIR)

        # Use custom title, or YouTube title, or fallback
        yt_title = custom_title or info.get("title") or info.get("fulltitle") or f"YouTube-{file_id}"
        yt_thumbnail = info.get("thumbnail") or ""
        yt_duration = info.get("duration") or 0

        logger.info(f"✅ YouTube download complete: '{yt_title}' ({yt_duration}s) → {mp3_path.name}")

        _status[file_id]["step"] = "transcribing"
        _status[file_id]["message"] = f"Transcribing: {yt_title}..."
        _status[file_id]["progress"] = 10

        # Run the standard processing pipeline (same as file upload)
        await _process_upload_with_metadata(file_id, mp3_path, yt_title, yt_thumbnail, yt_duration, url)

    except Exception as e:
        logger.error(f"YouTube processing failed for {file_id}: {e}")
        _status[file_id] = {
            "status": "error",
            "step": "failed",
            "progress": 0,
            "message": str(e),
            "_timestamp": time.time(),
        }


async def _process_upload_with_metadata(
    file_id: str, file_path: Path, title: str,
    thumbnail: str = "", duration: float = 0, source_url: str = ""
):
    """Extended processing pipeline with YouTube metadata support."""
    try:
        _status[file_id]["step"] = "transcribing"
        _status[file_id]["message"] = "Transcribing audio..."

        def progress_callback(current, total, msg):
            _status[file_id]["progress"] = int(10 + (current / total) * 40)
            _status[file_id]["message"] = msg

        transcript = await transcriber.transcribe_audio(file_id, file_path, title, progress_callback)

        try:
            rag_engine.index_transcript(transcript)
        except Exception as e:
            logger.warning(f"⚠️ Indexing failed: {e}")

        _status[file_id]["step"] = "summarizing"
        _status[file_id]["progress"] = 55
        _status[file_id]["message"] = "Generating summary..."

        summary_hi = await llm_engine.generate_summary(transcript.full_text, "hi")
        summary_en = await llm_engine.generate_summary(transcript.full_text, "en")
        summary_audio_hi = await tts_engine.generate_speech_async(summary_hi, "hi")
        summary_audio_en = await tts_engine.generate_speech_async(summary_en, "en")

        _status[file_id]["step"] = "explaining"
        _status[file_id]["progress"] = 75
        _status[file_id]["message"] = "Generating explanation..."

        explanation_hi = await llm_engine.generate_explanation(transcript.full_text, "hi")
        explanation_en = await llm_engine.generate_explanation(transcript.full_text, "en")
        explanation_audio_hi = await tts_engine.generate_speech_async(explanation_hi, "hi")
        explanation_audio_en = await tts_engine.generate_speech_async(explanation_en, "en")

        _status[file_id]["step"] = "generating_themes"
        _status[file_id]["progress"] = 90
        _status[file_id]["message"] = "Extracting themes..."

        themes_data = await llm_engine.generate_video_themes(transcript.full_text)

        try:
            video_data = {
                "id": file_id,
                "title": title,
                "title_hi": title,
                "description": f"Source: {source_url}" if source_url else f"Uploaded: {file_path.name}",
                "description_hi": f"स्रोत: {source_url}" if source_url else f"अपलोड: {file_path.name}",
                "thumbnail": thumbnail or f"/api/thumbnail/{file_id}",
                "video_url": source_url or "",
                "duration": duration or transcript.duration,
                "transcript": transcript.full_text,
                "transcript_chunks": [c.model_dump() for c in transcript.chunks],
                "summary_hi": summary_hi,
                "summary_en": summary_en,
                "explanation_hi": explanation_hi,
                "explanation_en": explanation_en,
                "main_topic": themes_data.get("main_topic", ""),
                "main_topic_en": themes_data.get("main_topic_en", ""),
                "themes": themes_data.get("themes", []),
                "themes_en": themes_data.get("themes_en", []),
                "key_teachings": themes_data.get("key_teachings", []),
                "summary_audio_hi": summary_audio_hi or None,
                "summary_audio_en": summary_audio_en or None,
                "explanation_audio_hi": explanation_audio_hi or None,
                "explanation_audio_en": explanation_audio_en or None,
                "category": "pravachan",
                "speaker": "Maharaj Ji",
            }
            factory = _get_session_factory()
            async with factory() as db:
                await crud.upsert_video(db, video_data)
            logger.info(f"✅ Persisted video content to database: {file_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to persist video content: {e}")

        _status[file_id] = {
            "status": "complete",
            "step": "done",
            "progress": 100,
            "message": "Processing complete!",
            "transcript": transcript,
            "summary": {"hi": summary_hi, "en": summary_en},
            "summary_audio": {"hi": summary_audio_hi, "en": summary_audio_en},
            "explanation": {"hi": explanation_hi, "en": explanation_en},
            "explanation_audio": {"hi": explanation_audio_hi, "en": explanation_audio_en},
            "themes_data": themes_data,
            "_timestamp": time.time(),
        }
        logger.info(f"✅ Completed processing: {file_id}")

    except Exception as e:
        logger.error(f"Processing failed for {file_id}: {e}")
        _status[file_id] = {
            "status": "error",
            "step": "failed",
            "progress": 0,
            "message": str(e),
            "_timestamp": time.time(),
        }


async def _process_upload(file_id: str, file_path: Path, filename: str):
    """Background: transcribe, generate summary & explanation with audio."""
    try:
        _status[file_id]["step"] = "transcribing"
        _status[file_id]["message"] = "Transcribing audio..."

        def progress_callback(current, total, msg):
            _status[file_id]["progress"] = int((current / total) * 50)
            _status[file_id]["message"] = msg

        transcript = await transcriber.transcribe_audio(file_id, file_path, filename, progress_callback)

        try:
            rag_engine.index_transcript(transcript)
        except Exception as e:
            logger.warning(f"⚠️ Indexing failed: {e}")

        _status[file_id]["step"] = "summarizing"
        _status[file_id]["progress"] = 55
        _status[file_id]["message"] = "Generating summary..."

        summary_hi = await llm_engine.generate_summary(transcript.full_text, "hi")
        summary_en = await llm_engine.generate_summary(transcript.full_text, "en")
        summary_audio_hi = await tts_engine.generate_speech_async(summary_hi, "hi")
        summary_audio_en = await tts_engine.generate_speech_async(summary_en, "en")

        _status[file_id]["step"] = "explaining"
        _status[file_id]["progress"] = 75
        _status[file_id]["message"] = "Generating explanation..."

        explanation_hi = await llm_engine.generate_explanation(transcript.full_text, "hi")
        explanation_en = await llm_engine.generate_explanation(transcript.full_text, "en")
        explanation_audio_hi = await tts_engine.generate_speech_async(explanation_hi, "hi")
        explanation_audio_en = await tts_engine.generate_speech_async(explanation_en, "en")

        _status[file_id]["step"] = "generating_themes"
        _status[file_id]["progress"] = 90
        _status[file_id]["message"] = "Extracting themes..."

        themes_data = await llm_engine.generate_video_themes(transcript.full_text)

        try:
            video_data = {
                "id": file_id,
                "title": transcript.title,
                "title_hi": transcript.title,
                "description": f"Uploaded: {filename}",
                "description_hi": f"अपलोड: {filename}",
                "thumbnail": f"/api/thumbnail/{file_id}",
                "duration": transcript.duration,
                "transcript": transcript.full_text,
                "transcript_chunks": [c.model_dump() for c in transcript.chunks],
                "summary_hi": summary_hi,
                "summary_en": summary_en,
                "explanation_hi": explanation_hi,
                "explanation_en": explanation_en,
                "main_topic": themes_data.get("main_topic", ""),
                "main_topic_en": themes_data.get("main_topic_en", ""),
                "themes": themes_data.get("themes", []),
                "themes_en": themes_data.get("themes_en", []),
                "key_teachings": themes_data.get("key_teachings", []),
                "summary_audio_hi": summary_audio_hi or None,
                "summary_audio_en": summary_audio_en or None,
                "explanation_audio_hi": explanation_audio_hi or None,
                "explanation_audio_en": explanation_audio_en or None,
                "category": "pravachan",
                "speaker": "Maharaj Ji",
            }
            factory = _get_session_factory()
            async with factory() as db:
                await crud.upsert_video(db, video_data)
            logger.info(f"✅ Persisted video content to database: {file_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to persist video content: {e}")

        _status[file_id] = {
            "status": "complete",
            "step": "done",
            "progress": 100,
            "message": "Processing complete!",
            "transcript": transcript,
            "summary": {"hi": summary_hi, "en": summary_en},
            "summary_audio": {"hi": summary_audio_hi, "en": summary_audio_en},
            "explanation": {"hi": explanation_hi, "en": explanation_en},
            "explanation_audio": {"hi": explanation_audio_hi, "en": explanation_audio_en},
            "themes_data": themes_data,
            "_timestamp": time.time()
        }
        logger.info(f"✅ Completed processing: {file_id}")

    except Exception as e:
        logger.error(f"Processing failed for {file_id}: {e}")
        _status[file_id] = {
            "status": "error",
            "step": "failed",
            "progress": 0,
            "message": str(e),
            "_timestamp": time.time()
        }


@router.get("/transcript/{transcript_id}")
async def get_transcript(transcript_id: str, language: str = "hi"):
    """Get transcript status, content, summary, and explanation."""
    if transcript_id in _status:
        status = _status[transcript_id]

        if status["status"] == "processing":
            return {
                "id": transcript_id,
                "status": "processing",
                "step": status["step"],
                "progress": status["progress"],
                "message": status["message"]
            }

        if status["status"] == "error":
            return {
                "id": transcript_id,
                "status": "error",
                "step": "failed",
                "progress": 0,
                "message": status["message"]
            }

        if status["status"] == "complete":
            t = status["transcript"]
            lang = language if language in ["hi", "en"] else "hi"
            return {
                "id": t.id,
                "title": t.title,
                "filename": t.filename,
                "duration": t.duration,
                "status": "complete",
                "full_text": t.full_text,
                "chunks": [c.model_dump() for c in t.chunks],
                "summary": status["summary"].get(lang, ""),
                "summary_audio": status["summary_audio"].get(lang, ""),
                "explanation": status["explanation"].get(lang, ""),
                "explanation_audio": status["explanation_audio"].get(lang, "")
            }

    t = transcriber.load_transcript(transcript_id)
    if not t:
        raise HTTPException(404, "Transcript not found")

    return {
        "id": t.id,
        "title": t.title,
        "filename": t.filename,
        "duration": t.duration,
        "status": "complete",
        "full_text": t.full_text,
        "chunks": [c.model_dump() for c in t.chunks]
    }


@router.get("/transcripts")
async def list_transcripts():
    """List all transcripts."""
    return transcriber.list_transcripts()

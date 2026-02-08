"""
Divya Vaani AI - Main API Routes
API for pre-processed video content with real-time Q&A.
Videos are pre-loaded with transcripts, summaries, and explanations.
Q&A is generated on-demand using RAG.
"""
import os
import uuid
import time
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request, Depends, Header
from fastapi.responses import FileResponse

from config import settings
from data.schema import (
    UploadResponse, TranscriptResponse, ChatRequest, ChatResponse,
    SourceType, TTSRequest, TTSResponse
)
from data.videos_content import (
    get_all_videos, get_video_detail, init_videos_content,
    VideoContent, add_video_content, update_video_content, delete_video_content
)
from core import transcriber, llm_engine, rag_engine, tts_engine

logger = logging.getLogger(__name__)
router = APIRouter()

# Rate limiter (initialized in run.py, accessed via app.state)
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)

# In-memory status store for processing jobs (bounded)
_status: Dict[str, dict] = {}
MAX_STATUS_ENTRIES = 100

# Max upload file size from config
MAX_UPLOAD_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Status TTL: 1 hour
STATUS_TTL_SECONDS = 3600

# Input limits
MAX_QUESTION_LENGTH = 1000
MAX_TTS_TEXT_LENGTH = 2000


def _safe_path(base_dir: Path, filename: str) -> Path:
    """Resolve a path and ensure it stays within base_dir (prevents path traversal)."""
    resolved = (base_dir / filename).resolve()
    base_resolved = base_dir.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        raise HTTPException(400, "Invalid filename")
    return resolved


def _verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """Dependency to verify admin API key for protected endpoints."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(403, "Admin access disabled: ADMIN_API_KEY not configured on server.")
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(403, "Invalid or missing admin API key. Set X-Admin-Key header.")


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
    # Enforce max entries - remove oldest completed entries
    if len(_status) > MAX_STATUS_ENTRIES:
        completed = sorted(
            [(k, v) for k, v in _status.items() if v.get("status") in ("complete", "error")],
            key=lambda x: x[1].get("_timestamp", 0)
        )
        for k, _ in completed[:len(_status) - MAX_STATUS_ENTRIES]:
            del _status[k]


# ========== Upload & Transcript ==========

@router.post("/upload", response_model=UploadResponse, dependencies=[Depends(_verify_admin_key)])
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_file(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload audio/video for transcription.
    Returns immediately with file_id, processing happens in background.
    Requires X-Admin-Key header if ADMIN_API_KEY is set.
    """
    # Validate file type
    allowed_types = [".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg", ".flac"]
    file_ext = Path(file.filename or "unknown").suffix.lower()
    
    if file_ext not in allowed_types:
        raise HTTPException(400, f"File type {file_ext} not supported. Use: {allowed_types}")
    
    # Check Content-Length header first (fast reject before reading body)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            413,
            f"File too large. Max allowed: {settings.MAX_UPLOAD_SIZE_MB} MB"
        )
    
    # Generate unique ID
    file_id = str(uuid.uuid4())[:12]
    
    # Save uploaded file - stream to disk instead of reading into memory
    file_path = settings.UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        file_size = 0
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # Read 1MB at a time
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
        
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"Uploaded: {file.filename} ({file_size_mb:.1f} MB)")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {e}")
    
    # Cleanup old status entries
    _cleanup_old_status()
    
    # Initialize status
    _status[file_id] = {
        "status": "processing",
        "step": "transcribing",
        "progress": 0,
        "message": "Starting transcription...",
        "_timestamp": time.time()
    }
    
    # Start background processing
    background_tasks.add_task(_process_upload, file_id, file_path, file.filename)
    
    return UploadResponse(
        file_id=file_id,
        filename=file.filename,
        status="processing",
        message="Upload successful. Transcription started."
    )


async def _process_upload(file_id: str, file_path: Path, filename: str):
    """Background: transcribe, generate summary & explanation with audio."""
    try:
        # Step 1: Transcribe
        _status[file_id]["step"] = "transcribing"
        _status[file_id]["message"] = "Transcribing audio..."
        
        def progress_callback(current, total, msg):
            _status[file_id]["progress"] = int((current / total) * 50)
            _status[file_id]["message"] = msg
        
        transcript = await transcriber.transcribe_audio(
            file_id, file_path, filename, progress_callback
        )
        
        # Index for RAG search
        try:
            rag_engine.index_transcript(transcript)
        except Exception as e:
            logger.warning(f"⚠️ Indexing failed: {e}")
        
        # Step 2: Generate Summary (Hindi)
        _status[file_id]["step"] = "summarizing"
        _status[file_id]["progress"] = 55
        _status[file_id]["message"] = "Generating summary..."
        
        summary_hi = await llm_engine.generate_summary(transcript.full_text, "hi")
        summary_en = await llm_engine.generate_summary(transcript.full_text, "en")
        
        # Generate summary audio (Edge TTS - fast)
        summary_audio_hi = await tts_engine.generate_speech_async(summary_hi, "hi")
        summary_audio_en = await tts_engine.generate_speech_async(summary_en, "en")
        
        # Step 3: Generate Explanation
        _status[file_id]["step"] = "explaining"
        _status[file_id]["progress"] = 75
        _status[file_id]["message"] = "Generating explanation..."
        
        explanation_hi = await llm_engine.generate_explanation(transcript.full_text, "hi")
        explanation_en = await llm_engine.generate_explanation(transcript.full_text, "en")
        
        # Generate explanation audio (Edge TTS - fast)
        explanation_audio_hi = await tts_engine.generate_speech_async(explanation_hi, "hi")
        explanation_audio_en = await tts_engine.generate_speech_async(explanation_en, "en")
        
        # Step 4: Generate Themes and Key Teachings
        _status[file_id]["step"] = "generating_themes"
        _status[file_id]["progress"] = 90
        _status[file_id]["message"] = "Extracting themes..."
        
        themes_data = await llm_engine.generate_video_themes(transcript.full_text)
        
        # Persist to videos_content.json so data survives server restarts
        try:
            video_content = VideoContent(
                id=file_id,
                title=transcript.title,
                title_hi=transcript.title,
                description=f"Uploaded: {filename}",
                description_hi=f"अपलोड: {filename}",
                thumbnail=f"/api/thumbnail/{file_id}",
                duration=transcript.duration,
                transcript=transcript.full_text,
                transcript_chunks=[c.model_dump() for c in transcript.chunks],
                summary_hi=summary_hi,
                summary_en=summary_en,
                explanation_hi=explanation_hi,
                explanation_en=explanation_en,
                main_topic=themes_data.get("main_topic", ""),
                main_topic_en=themes_data.get("main_topic_en", ""),
                themes=themes_data.get("themes", []),
                themes_en=themes_data.get("themes_en", []),
                key_teachings=themes_data.get("key_teachings", []),
                summary_audio_hi=summary_audio_hi or None,
                summary_audio_en=summary_audio_en or None,
                explanation_audio_hi=explanation_audio_hi or None,
                explanation_audio_en=explanation_audio_en or None,
                created_at=datetime.now().isoformat(),
                category="pravachan",
                speaker="Maharaj Ji"
            )
            add_video_content(video_content)
            logger.info(f"✅ Persisted video content to disk: {file_id}")
        except Exception as e:
            logger.error(f"⚠️ Failed to persist video content: {e}")

        # Store results in memory for immediate polling
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
    
    # Check in-memory status first
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
            raise HTTPException(500, status["message"])
        
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
    
    # Try loading from disk
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


# ========== Pre-loaded Video Content ==========

@router.get("/videos")
async def list_videos():
    """Get all pre-loaded videos with basic info for cards."""
    try:
        videos = get_all_videos()
        return {"videos": videos, "total": len(videos)}
    except Exception as e:
        logger.error(f"Failed to get videos: {e}")
        raise HTTPException(500, f"Failed to get videos: {e}")


@router.get("/videos/{video_id}")
async def get_video(video_id: str, language: str = "hi"):
    """Get full video content including transcript, summary, and explanation."""
    video = get_video_detail(video_id, language)
    
    if not video:
        raise HTTPException(404, "Video not found")
    
    return video


@router.get("/videos/{video_id}/summary")
async def get_video_summary(video_id: str, language: str = "hi"):
    """Get video summary and explanation."""
    video = get_video_detail(video_id, language)
    
    if not video:
        raise HTTPException(404, "Video not found")
    
    return {
        "id": video_id,
        "summary": video.get("summary", ""),
        "summary_hi": video.get("summary_hi", ""),
        "summary_en": video.get("summary_en", ""),
        "explanation": video.get("explanation", ""),
        "explanation_hi": video.get("explanation_hi", ""),
        "explanation_en": video.get("explanation_en", ""),
        "summary_audio": video.get("summary_audio", ""),
        "explanation_audio": video.get("explanation_audio", "")
    }


@router.post("/videos/{video_id}/generate-summary", dependencies=[Depends(_verify_admin_key)])
async def generate_video_summary(video_id: str, background_tasks: BackgroundTasks):
    """Generate summary and explanation for a video on demand. Requires admin key."""
    video = get_video_detail(video_id, "hi")
    if not video:
        raise HTTPException(404, "Video not found")
    
    # Check if already has summary
    if video.get("summary_hi") and video.get("summary_en"):
        return {"status": "exists", "message": "Summary already exists"}
    
    # Generate in background
    async def generate_task():
        try:
            transcript = video.get("transcript", "")
            if not transcript:
                return
            
            # Generate summaries
            summary_hi = await llm_engine.generate_summary(transcript, "hi")
            summary_en = await llm_engine.generate_summary(transcript, "en")
            explanation_hi = await llm_engine.generate_explanation(transcript, "hi")
            explanation_en = await llm_engine.generate_explanation(transcript, "en")
            
            # Update video content
            update_video_content(video_id, {
                "summary_hi": summary_hi,
                "summary_en": summary_en,
                "explanation_hi": explanation_hi,
                "explanation_en": explanation_en
            })
            
            logger.info(f"✅ Generated summary for video: {video_id}")
        except Exception as e:
            logger.error(f"Failed to generate summary for {video_id}: {e}")
    
    background_tasks.add_task(generate_task)
    
    return {"status": "generating", "message": "Summary generation started"}


@router.delete("/videos/{video_id}", dependencies=[Depends(_verify_admin_key)])
async def delete_video(video_id: str):
    """Delete a video and all its associated data. Requires admin key."""
    video = get_video_detail(video_id, "hi")
    if not video:
        raise HTTPException(404, "Video not found")

    # Delete from persistent store
    delete_video_content(video_id)

    # Delete associated files
    for path in [
        settings.UPLOAD_DIR / f"{video_id}.mp4",
        settings.UPLOAD_DIR / f"{video_id}.mp3",
        settings.TRANSCRIPT_DIR / f"{video_id}.json",
    ]:
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    # Delete thumbnail
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        thumb = settings.DATA_DIR / "thumbnails" / f"{video_id}{ext}"
        if thumb.exists():
            try:
                thumb.unlink()
            except Exception:
                pass

    # Remove from in-memory status
    _status.pop(video_id, None)

    logger.info(f"\u2705 Deleted video: {video_id}")
    return {"status": "deleted", "id": video_id}


@router.get("/thumbnail/{video_id}")
async def get_thumbnail(video_id: str):
    """Serve video thumbnail image."""
    # Sanitize video_id - only allow alphanumeric, dash, underscore
    if not video_id.replace('-', '').replace('_', '').isalnum():
        raise HTTPException(400, "Invalid video ID")
    
    thumbnail_dir = settings.DATA_DIR / "thumbnails"
    
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        path = _safe_path(thumbnail_dir, f"{video_id}{ext}")
        if path.exists():
            return FileResponse(path)
    
    default_thumb = thumbnail_dir / "default.jpg"
    if default_thumb.exists():
        return FileResponse(default_thumb)
    
    raise HTTPException(404, "Thumbnail not found")


@router.get("/video/{video_id}")
async def get_video_file(video_id: str):
    """Serve uploaded video file."""
    # Sanitize video_id
    if not video_id.replace('-', '').replace('_', '').isalnum():
        raise HTTPException(400, "Invalid video ID")
    
    upload_dir = settings.DATA_DIR / "uploads"
    
    for ext in [".webm", ".mp4", ".mkv", ".avi", ".mov", ".m4v"]:
        path = _safe_path(upload_dir, f"{video_id}{ext}")
        if path.exists():
            media_types = {
                ".webm": "video/webm",
                ".mp4": "video/mp4",
                ".mkv": "video/x-matroska",
                ".avi": "video/x-msvideo",
                ".mov": "video/quicktime",
                ".m4v": "video/x-m4v"
            }
            return FileResponse(
                path, 
                media_type=media_types.get(ext, "video/mp4"),
                filename=f"{video_id}{ext}"
            )
    
    raise HTTPException(404, "Video file not found")


# ========== Chat / Q&A ==========

def _expand_question_for_search(question: str) -> str:
    """
    Expand the user's question with spiritual keywords to improve semantic search.
    This helps find relevant content when user asks emotional questions.
    """
    # Map common emotional/life questions to spiritual keywords
    expansion_keywords = {
        # Negative emotions / life problems
        "don't want to live": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय कमजोर",
        "want to die": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय मरना",
        "hopeless": "परेशान दुख धैर्य गंभीर विपत्ति समाधान",
        "depressed": "परेशान दुख कमजोर धैर्य गंभीर भगवान कृपा",
        "sad": "परेशान दुख धैर्य गंभीर भगवान कृपा",
        "struggling": "परेशान विपत्ति समस्या धैर्य गंभीर",
        "difficult": "विपत्ति समस्या धैर्य गंभीर समाधान",
        "problem": "समस्या विपत्ति समाधान धैर्य",
        "suffering": "दुख पीड़ा धैर्य भगवदाश्रय",
        "pain": "पीड़ा दुख धैर्य सहन भगवदाश्रय",
        "fear": "भय डर धैर्य भगवदाश्रय",
        "anxiety": "परेशान चिंता धैर्य गंभीर",
        "worried": "परेशान चिंता धैर्य गंभीर",
        "जीना नहीं": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय",
        "मरना": "जीवन परेशान दुख धैर्य सेवा मृत्यु",
        "परेशान": "परेशान दुख धैर्य गंभीर समाधान",
        "दुखी": "दुख परेशान धैर्य भगवान कृपा",
    }
    
    expanded = question
    question_lower = question.lower()
    
    for key, expansion in expansion_keywords.items():
        if key in question_lower:
            expanded = f"{question} {expansion}"
            break
    
    return expanded


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat(request: Request, chat_request: ChatRequest):
    """
    Ask a question - answers come from pre-loaded spiritual discourses.
    Rate limited to prevent API abuse.
    """
    question = chat_request.question.strip()
    language = chat_request.language if chat_request.language in ["hi", "en"] else "hi"
    
    if not question:
        raise HTTPException(400, "Question cannot be empty")
    
    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(400, f"Question too long. Max {MAX_QUESTION_LENGTH} characters.")
    
    # Handle greetings - don't search for teachings, just respond politely
    greetings_en = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "namaste"]
    greetings_hi = ["नमस्ते", "नमस्कार", "हेलो", "हाय", "राधे राधे", "जय श्री कृष्ण", "हरि ॐ"]
    
    question_lower = question.lower().strip()
    is_greeting = question_lower in greetings_en or question in greetings_hi or len(question) < 5
    
    if is_greeting:
        if language == "hi":
            greeting_response = "🙏 राधे राधे! मैं दिव्य वाणी AI हूं। आप महाराज जी के प्रवचनों से संबंधित कोई भी प्रश्न पूछ सकते हैं। जैसे - 'भक्ति क्या है?', 'मन को शांत कैसे करें?', 'जीवन में धैर्य कैसे रखें?'"
        else:
            greeting_response = "🙏 Radhe Radhe! I am Divya Vaani AI. You can ask any question related to Maharaj Ji's discourses. For example - 'What is devotion?', 'How to find peace of mind?', 'How to have patience in life?'"
        
        return ChatResponse(
            answer=greeting_response,
            source_type=SourceType.NOT_FOUND,
            source_reference="",
            audio_url=""
        )
    
    # transcript_id can be either a video_id or transcript_id
    content_id = chat_request.transcript_id
    
    # Detect if question is in English and translate for better Hindi transcript search
    is_english = llm_engine.is_english_text(question)
    search_query = question
    
    if is_english:
        # Translate English question to Hindi for better semantic matching
        hindi_question = await llm_engine.translate_to_hindi(question)
        search_query = f"{question} {hindi_question}"  # Search with both
    
    # Search both transcripts AND Gita, then pick the best source
    transcript_results = []
    gita_results = []
    best_transcript_score = 0.0
    best_gita_score = 0.0
    
    # Lower thresholds for English queries (cross-lingual matching is harder)
    transcript_threshold = 0.45 if is_english else 0.60
    gita_threshold = 0.55 if is_english else 0.75
    
    # Search transcripts if any exist
    if content_id or rag_engine.has_transcripts():
        # Expand question with spiritual keywords for better semantic search
        expanded_query = _expand_question_for_search(search_query)
        
        # Search with expanded query (returns chunks with scores)
        transcript_results = rag_engine.search_transcripts_with_scores(
            expanded_query, 
            transcript_id=content_id,
            top_k=5
        )
        
        # If no results with expanded query, try original question
        if not transcript_results:
            transcript_results = rag_engine.search_transcripts_with_scores(
                search_query, 
                transcript_id=content_id,
                top_k=5
            )
        
        if transcript_results:
            best_transcript_score = transcript_results[0]["score"]
    
    # Always search Gita as potential fallback (use search_query for cross-lingual support)
    gita_results = rag_engine.search_gita(search_query, top_k=3)
    if gita_results:
        best_gita_score = gita_results[0]["score"]
    
    # Decision logic for choosing source (use dynamic thresholds based on language)
    GOOD_TRANSCRIPT_THRESHOLD = transcript_threshold
    GOOD_GITA_THRESHOLD = gita_threshold
    
    # Check if question explicitly asks about Gita/Arjuna/Krishna dialogue
    question_lower = question.lower()
    gita_keywords_en = ["gita", "geeta", "arjun", "bhagavad", "bhagwat", "chapter", "verse"]
    gita_keywords_hi = ["गीता", "अर्जुन", "भगवद", "श्लोक", "अध्याय", "कृष्ण ने अर्जुन"]
    
    is_explicit_gita_question = (
        any(kw in question_lower for kw in gita_keywords_en) or
        any(kw in question for kw in gita_keywords_hi)
    )
    
    use_transcript = False
    use_gita = False
    
    # If explicitly asking about Gita AND Gita has results, always use Gita
    if is_explicit_gita_question and gita_results:
        use_gita = True
    # If Gita has excellent match and transcript doesn't have significantly better match
    elif gita_results and best_gita_score >= GOOD_GITA_THRESHOLD:
        if not transcript_results or best_transcript_score < best_gita_score:
            use_gita = True
        else:
            # Transcript has equal or better score — prefer pravachan over Gita
            use_transcript = True
    # Use transcript if we're not using Gita and it has good relevance
    elif transcript_results and best_transcript_score >= GOOD_TRANSCRIPT_THRESHOLD:
        use_transcript = True
    # Fallback to transcript if available
    elif transcript_results:
        use_transcript = True
    
    if use_transcript and transcript_results:
        chunks = [r["chunk"] for r in transcript_results]
        
        # Build rich context from chunks
        context_parts = []
        for c in chunks:
            timestamp = f"[{_format_time(c.start_time)} - {_format_time(c.end_time)}]"
            context_parts.append(f"{timestamp}: {c.text}")
        
        context = "\n\n".join(context_parts)
        
        # Generate compassionate answer from the spiritual discourse
        answer = await llm_engine.generate_answer(
            question, context, SourceType.PRAVACHAN, language
        )
        
        return ChatResponse(
            answer=answer,
            source_type=SourceType.PRAVACHAN,
            source_reference=f"Based on {len(chunks)} segments from the discourse (relevance: {best_transcript_score:.0%})",
            audio_url=""
        )
    
    # Use Bhagavad Gita
    if use_gita and gita_results:
        # Generate answer from Gita verses
        answer = await llm_engine.generate_gita_answer(question, gita_results, language)
        
        # Build verse references
        verse_refs = [f"Chapter {v['verse'].chapter}, Verse {v['verse'].verse}" for v in gita_results]
        
        return ChatResponse(
            answer=answer,
            source_type=SourceType.GITA,
            source_reference=f"📖 Bhagavad Gita - {', '.join(verse_refs)}",
            audio_url=""
        )
    
    # Not found response
    not_found = await llm_engine.generate_not_found(language)
    
    return ChatResponse(
        answer=not_found,
        source_type=SourceType.NOT_FOUND,
        source_reference="",
        audio_url=""
    )


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


# ========== Speech ==========

@router.post("/transcribe-voice")
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def transcribe_voice_input(request: Request, audio: UploadFile = File(...), language: str = None):
    """Transcribe voice input (for asking questions by voice)."""
    # Save temp file - stream to disk
    temp_path = settings.UPLOAD_DIR / f"voice_{uuid.uuid4()}.webm"
    
    try:
        file_size = 0
        max_voice_size = 10 * 1024 * 1024  # 10MB max for voice input
        with open(temp_path, "wb") as f:
            while chunk := await audio.read(1024 * 64):  # 64KB chunks
                file_size += len(chunk)
                if file_size > max_voice_size:
                    raise HTTPException(413, "Voice recording too large (max 10MB)")
                f.write(chunk)
        
        # Transcribe — let Whisper auto-detect language for best accuracy
        text = await transcriber.transcribe_voice(temp_path, language=language)
        
        return {"text": text}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Voice transcription failed: {e}")
    finally:
        # Cleanup
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
        tts_request.text, 
        tts_request.language, 
        tts_request.gender
    )
    
    if not audio_url:
        raise HTTPException(500, "TTS generation failed")
    
    return TTSResponse(audio_url=audio_url)


@router.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve audio files."""
    # Only allow safe filenames (alphanumeric, dash, underscore, dot)
    if not all(c.isalnum() or c in '-_.' for c in filename):
        raise HTTPException(400, "Invalid filename")
    path = _safe_path(settings.AUDIO_DIR, filename)
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/mpeg")


# ========== TTS Status ==========

@router.get("/tts/status")
async def tts_status():
    """Get status of TTS system."""
    return {
        "mode": settings.TTS_MODE,
        "engines": ["gTTS", "Edge TTS"],
        "status": "active",
        "note": "Custom person-specific TTS model support coming in next version"
    }

"""
Divya Vaani AI - Main API Routes
API for pre-processed video content with real-time Q&A.
Videos are pre-loaded with transcripts, summaries, and explanations.
Q&A is generated on-demand using RAG.
"""
import os
import uuid
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from config import settings
from data.schema import (
    UploadResponse, TranscriptResponse, ChatRequest, ChatResponse,
    SourceType, TTSRequest, TTSResponse
)
from data.videos_content import (
    get_all_videos, get_video_detail, init_videos_content,
    VideoContent, add_video_content, update_video_content
)
from core import transcriber, llm_engine, rag_engine, tts_engine

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory status store for processing jobs
_status: Dict[str, dict] = {}


# ========== Upload & Transcript ==========

@router.post("/upload", response_model=UploadResponse)
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload audio/video for transcription.
    Returns immediately with file_id, processing happens in background.
    """
    # Validate file type
    allowed_types = [".mp3", ".mp4", ".wav", ".m4a", ".webm", ".ogg", ".flac"]
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_types:
        raise HTTPException(400, f"File type {file_ext} not supported. Use: {allowed_types}")
    
    # Generate unique ID
    file_id = str(uuid.uuid4())[:12]
    file_path = settings.UPLOAD_DIR / f"{file_id}{file_ext}"
    max_size_mb = getattr(settings, 'MAX_UPLOAD_SIZE_MB', 500)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # Stream upload to disk with size check (avoids loading entire file into memory)
    try:
        total_bytes = 0
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                total_bytes += len(chunk)
                if total_bytes > max_size_bytes:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(400, f"File too large. Maximum: {max_size_mb}MB")
                f.write(chunk)
        
        file_size_mb = total_bytes / (1024 * 1024)
        
        logger.info(f"📁 Uploaded: {file.filename} ({file_size_mb:.1f} MB)")
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions (like size limit)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Failed to save file: {e}")
    
    # Initialize status
    _status[file_id] = {
        "status": "processing",
        "step": "transcribing",
        "progress": 0,
        "message": "Starting transcription..."
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
        
        # Generate summary audio (using cloned voice)
        summary_audio_hi = await tts_engine.generate_speech_async(summary_hi, "hi", mode="clone")
        summary_audio_en = await tts_engine.generate_speech_async(summary_en, "en", mode="clone")
        
        # Step 3: Generate Explanation
        _status[file_id]["step"] = "explaining"
        _status[file_id]["progress"] = 75
        _status[file_id]["message"] = "Generating explanation..."
        
        explanation_hi = await llm_engine.generate_explanation(transcript.full_text, "hi")
        explanation_en = await llm_engine.generate_explanation(transcript.full_text, "en")
        
        # Generate explanation audio (using cloned voice)
        explanation_audio_hi = await tts_engine.generate_speech_async(explanation_hi, "hi", mode="clone")
        explanation_audio_en = await tts_engine.generate_speech_async(explanation_en, "en", mode="clone")
        
        # Store results
        _status[file_id] = {
            "status": "complete",
            "step": "done",
            "progress": 100,
            "message": "Processing complete!",
            "transcript": transcript,
            "summary": {"hi": summary_hi, "en": summary_en},
            "summary_audio": {"hi": summary_audio_hi, "en": summary_audio_en},
            "explanation": {"hi": explanation_hi, "en": explanation_en},
            "explanation_audio": {"hi": explanation_audio_hi, "en": explanation_audio_en}
        }
        
        logger.info(f"✅ Completed processing: {file_id}")
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        _status[file_id] = {
            "status": "error",
            "step": "failed",
            "progress": 0,
            "message": str(e)
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
                "chunks": [c.to_dict() for c in t.chunks],
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
        "chunks": [c.to_dict() for c in t.chunks]
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


@router.post("/videos/{video_id}/generate-summary")
async def generate_video_summary(video_id: str, background_tasks: BackgroundTasks):
    """Generate summary and explanation for a video on demand."""
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


@router.get("/thumbnail/{video_id}")
async def get_thumbnail(video_id: str):
    """Serve video thumbnail image."""
    # Security: sanitize video_id to prevent path traversal
    import re
    if not re.match(r'^[a-zA-Z0-9_\-]+$', video_id):
        raise HTTPException(400, "Invalid video ID")
    
    thumbnail_dir = settings.DATA_DIR / "thumbnails"
    
    # Try different extensions
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        path = thumbnail_dir / f"{video_id}{ext}"
        if path.exists():
            return FileResponse(path)
    
    # Return default thumbnail
    default_thumb = thumbnail_dir / "default.jpg"
    if default_thumb.exists():
        return FileResponse(default_thumb)
    
    raise HTTPException(404, "Thumbnail not found")


# ========== Chat / Q&A ==========

def _expand_question_for_search(question: str) -> str:
    """
    Expand the user's question with spiritual keywords to improve semantic search.
    This helps find relevant content when user asks emotional questions.
    Maps common topics to Hindi spiritual terms used in discourses.
    """
    # Map common emotional/life questions to spiritual keywords
    expansion_keywords = {
        # Negative emotions / life problems
        "don't want to live": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय सहन कमजोर",
        "want to die": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय मरना सहन",
        "hopeless": "परेशान दुख धैर्य गंभीर विपत्ति समाधान सहनशीलता",
        "depressed": "परेशान दुख कमजोर धैर्य गंभीर भगवान कृपा सहन मन",
        "sad": "परेशान दुख धैर्य गंभीर भगवान कृपा मन शांति",
        "struggling": "परेशान विपत्ति समस्या धैर्य गंभीर सहन",
        "difficult": "विपत्ति समस्या धैर्य गंभीर समाधान सहन",
        "problem": "समस्या विपत्ति समाधान धैर्य सहन",
        "suffering": "दुख पीड़ा धैर्य भगवदाश्रय सहन",
        "pain": "पीड़ा दुख धैर्य सहन भगवदाश्रय",
        "fear": "भय डर धैर्य भगवदाश्रय विश्वास",
        "anxiety": "परेशान चिंता धैर्य गंभीर मन शांति",
        "worried": "परेशान चिंता धैर्य गंभीर मन नियंत्रण",
        "angry": "क्रोध गुस्सा शांति सहन धैर्य मन",
        "patience": "सहन धैर्य सहनशीलता शांति भक्त",
        "chanting": "नाम जप कीर्तन भजन राधा कृष्ण",
        "meditation": "ध्यान भजन नाम जप प्राणायाम",
        "devotion": "भक्ति सेवा समर्पण प्रेम भगवान",
        "mind control": "मन नियंत्रण दिनचर्या नियमावली इंद्रिय",
        "daily routine": "दिनचर्या नियमावली भजन प्राणायाम सेवा",
        "mistake": "गलती पाप क्षमा सुधार भगवान कृपा",
        "how to pray": "पूजा प्रार्थना भजन अर्चन सेवा विधि",
        "god": "भगवान ईश्वर प्रभु कृष्ण श्री",
        # Hindi keywords
        "जीना नहीं": "जीवन परेशान दुख धैर्य सेवा भगवदाश्रय सहन",
        "मरना": "जीवन परेशान दुख धैर्य सेवा मृत्यु सहन",
        "परेशान": "परेशान दुख धैर्य गंभीर समाधान सहन शांति",
        "दुखी": "दुख परेशान धैर्य भगवान कृपा सहन",
        "नाम जप": "नाम जप कीर्तन भजन राधा कृष्ण 24 घंटे",
        "मन": "मन नियंत्रण दिनचर्या इंद्रिय शांति",
        "भक्ति": "भक्ति सेवा समर्पण प्रेम भजन मार्ग",
        "गलती": "गलती पाप क्षमा सुधार भगवान कृपा बार-बार",
        "सहन": "सहन सहनशीलता धैर्य शांति भक्त",
        "क्रोध": "क्रोध गुस्सा शांति सहन धैर्य मन नियंत्रण",
        "प्राणायाम": "प्राणायाम श्वास ध्यान भजन शोधन",
        "दिनचर्या": "दिनचर्या नियमावली भजन प्राणायाम सेवा हलका भोजन",
    }
    
    expanded = question
    question_lower = question.lower()
    
    # Collect all matching expansions (not just first match)
    expansions = []
    for key, expansion in expansion_keywords.items():
        if key in question_lower:
            expansions.append(expansion)
    
    if expansions:
        expanded = f"{question} {' '.join(expansions)}"
    
    return expanded


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Ask a question - answers come from pre-loaded spiritual discourses.
    
    The system searches through ALL pravachans to find the most relevant
    spiritual guidance for the user's question, then provides wisdom
    from Maharaj Ji's teachings.
    
    Strategy:
    1. First search the specific video/transcript if provided
    2. ALWAYS also search ALL transcripts for best possible answer
    3. Merge results, prioritizing specific video matches
    4. Fall back to Bhagavad Gita if no transcript matches
    """
    question = request.question.strip()
    language = request.language if request.language in ["hi", "en"] else "hi"
    
    if not question:
        raise HTTPException(400, "Question cannot be empty")
    
    # transcript_id can be either a video_id or transcript_id
    content_id = request.transcript_id
    
    # Search transcripts if any exist
    if rag_engine.has_transcripts():
        # Expand question with spiritual keywords for better semantic search
        expanded_query = _expand_question_for_search(question)
        
        # Strategy: Search specific transcript AND all transcripts, merge results
        specific_chunks = []
        global_chunks = []
        
        # 1. Search specific transcript if provided
        if content_id:
            specific_chunks = rag_engine.search_transcripts(
                expanded_query, 
                transcript_id=content_id,
                top_k=5
            )
            if not specific_chunks:
                specific_chunks = rag_engine.search_transcripts(
                    question, 
                    transcript_id=content_id,
                    top_k=5
                )
        
        # 2. ALWAYS search ALL transcripts for the best possible answer
        global_chunks = rag_engine.search_transcripts(
            expanded_query, 
            transcript_id=None,  # Search ALL
            top_k=8
        )
        if not global_chunks:
            global_chunks = rag_engine.search_transcripts(
                question, 
                transcript_id=None,
                top_k=8
            )
        
        # 3. Merge: specific video chunks first, then global (deduplicated)
        seen_ids = set()
        merged_chunks = []
        
        for c in specific_chunks:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                merged_chunks.append(c)
        
        for c in global_chunks:
            if c.id not in seen_ids and len(merged_chunks) < 10:
                seen_ids.add(c.id)
                merged_chunks.append(c)
        
        if merged_chunks:
            # Build rich context from chunks — label each passage distinctly
            context_parts = []
            for idx, c in enumerate(merged_chunks, 1):
                timestamp = f"{_format_time(c.start_time)} - {_format_time(c.end_time)}"
                context_parts.append(f"Passage {idx} ({timestamp}):\n{c.text}")
            
            context = "\n\n".join(context_parts)
            
            # Generate answer - LLM will check relevance first
            answer = await llm_engine.generate_answer(
                question, context, SourceType.PRAVACHAN, language
            )
            
            # If LLM determined the question is not relevant to spiritual content
            if answer is None:
                not_found = await llm_engine.generate_not_found(language)
                return ChatResponse(
                    answer=not_found,
                    source_type=SourceType.NOT_FOUND,
                    source_reference="",
                    audio_url=""
                )
            
            # Skip TTS for faster response
            return ChatResponse(
                answer=answer,
                source_type=SourceType.PRAVACHAN,
                source_reference=f"Based on {len(merged_chunks)} segments from the discourses",
                audio_url=""
            )
    
    # Fallback: Search Bhagavad Gita for relevant wisdom
    try:
        gita_results = rag_engine.search_gita(question, top_k=3)
        if gita_results:
            # Build context from Gita verses
            context_parts = []
            for result in gita_results:
                verse = result["verse"]
                ref = f"[Bhagavad Gita {verse.chapter}.{verse.verse}]"
                text = verse.hindi if language == "hi" else verse.english
                context_parts.append(f"{ref}: {text}")
            
            context = "\n\n".join(context_parts)
            
            answer = await llm_engine.generate_answer(
                question, context, SourceType.GITA, language
            )
            
            # If LLM says NOT_RELEVANT even for Gita context, fall through to not_found
            if answer is not None:
                return ChatResponse(
                    answer=answer,
                    source_type=SourceType.GITA,
                    source_reference=f"Based on {len(gita_results)} verses from Bhagavad Gita",
                    audio_url=""
                )
    except Exception as e:
        logger.warning(f"Gita search failed: {e}")
    
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
async def transcribe_voice_input(audio: UploadFile = File(...)):
    """Transcribe voice input (for asking questions by voice)."""
    # Save temp file
    temp_path = settings.UPLOAD_DIR / f"voice_{uuid.uuid4()}.webm"
    
    try:
        content = await audio.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        
        # Transcribe
        text = await transcriber.transcribe_voice(temp_path)
        
        return {"text": text}
        
    except Exception as e:
        raise HTTPException(500, f"Voice transcription failed: {e}")
    finally:
        # Cleanup
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as e:
                logger.debug(f"Could not delete temp voice file: {e}")


@router.post("/tts", response_model=TTSResponse)
async def synthesize_speech(request: TTSRequest):
    """Convert text to speech (uses cloned voice)."""
    audio_url = await tts_engine.generate_speech_async(request.text, request.language, mode="clone")
    
    if not audio_url:
        raise HTTPException(500, "TTS generation failed")
    
    return TTSResponse(audio_url=audio_url)


@router.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve audio files."""
    # Security: sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    if safe_name != filename or '..' in filename:
        raise HTTPException(400, "Invalid filename")
    path = settings.AUDIO_DIR / safe_name
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/mpeg")


# ========== Voice Cloning ==========

@router.get("/voice-cloning/status")
async def voice_cloning_status():
    """Get status of voice cloning system."""
    try:
        from core.voice_cloner import get_voice_cloning_status, is_voice_cloning_available, REFERENCE_AUDIO_FILENAME
        status = get_voice_cloning_status()
        status["enabled"] = getattr(settings, 'USE_VOICE_CLONING', False)
        status["required_file"] = REFERENCE_AUDIO_FILENAME
        return status
    except ImportError:
        return {
            "available": False,
            "enabled": False,
            "error": "Voice cloning module not found. Install with: pip install TTS",
            "required_file": "maharaj_audio.mp3"
        }


@router.get("/voice-cloning/reference-files")
async def list_reference_files():
    """Get information about the designated reference audio file."""
    try:
        from core.voice_cloner import get_reference_audio_path, REFERENCE_AUDIO_FILENAME
        
        ref_path = get_reference_audio_path()
        
        if ref_path and ref_path.exists():
            return {
                "status": "found",
                "required_file": REFERENCE_AUDIO_FILENAME,
                "path": str(ref_path),
                "size_mb": round(ref_path.stat().st_size / (1024 * 1024), 2),
                "message": "Reference audio is ready for voice cloning"
            }
        else:
            return {
                "status": "not_found",
                "required_file": REFERENCE_AUDIO_FILENAME,
                "expected_location": "Input/maharaj_audio.mp3",
                "message": f"Please place {REFERENCE_AUDIO_FILENAME} in the Input folder"
            }
    except ImportError:
        return {
            "status": "error",
            "required_file": "maharaj_audio.mp3",
            "message": "Voice cloning module not available"
        }


# ========== Admin Panel API ==========

from pydantic import BaseModel as PydanticBaseModel

class AddYouTubeRequest(PydanticBaseModel):
    url: str
    speaker: str = "Maharaj Ji"
    category: str = "pravachan"

class UpdateVideoUrlRequest(PydanticBaseModel):
    video_url: str

# In-memory job status store for YouTube processing
_youtube_jobs: dict = {}

@router.post("/admin/youtube")
async def add_youtube_video(request: AddYouTubeRequest, background_tasks: BackgroundTasks):
    """
    Admin: Add a YouTube video - starts background processing pipeline.
    Downloads audio → transcribes → indexes → generates summary & explanation.
    Returns a job_id for tracking progress.
    """
    from core.youtube_pipeline import extract_youtube_id, get_youtube_info
    
    # Validate URL
    yt_id = extract_youtube_id(request.url)
    if not yt_id:
        raise HTTPException(400, "Invalid YouTube URL. Please provide a valid YouTube link.")
    
    # Check for duplicate YouTube URL
    existing_videos = get_all_videos()
    for v in existing_videos:
        if v.get("video_url") and extract_youtube_id(v["video_url"]) == yt_id:
            raise HTTPException(409, f"This YouTube video is already added (ID: {v['id']})")
    
    # Get video info first (fast, no download)
    try:
        info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: get_youtube_info(request.url)
        )
    except Exception as e:
        raise HTTPException(400, f"Could not fetch video info: {str(e)}")
    
    # Create job
    job_id = str(uuid.uuid4())[:12]
    _youtube_jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "step": "queued",
        "progress": 0,
        "message": "Queued for processing...",
        "youtube_url": request.url,
        "youtube_id": yt_id,
        "title": info.get("title", ""),
        "duration": info.get("duration", 0),
        "video_id": None,
        "error": None,
        "created_at": datetime.now().isoformat(),
    }
    
    # Start background processing
    background_tasks.add_task(
        _process_youtube_job, job_id, request.url, request.speaker, request.category
    )
    
    return {
        "job_id": job_id,
        "status": "queued",
        "title": info.get("title", ""),
        "duration": info.get("duration", 0),
        "youtube_id": yt_id,
        "message": "Processing started. Use GET /api/admin/youtube/{job_id} to track progress."
    }


async def _process_youtube_job(job_id: str, url: str, speaker: str, category: str):
    """Background task: process YouTube video through full pipeline."""
    from core.youtube_pipeline import process_youtube_video
    
    def progress_callback(step: str, pct: int, msg: str):
        _youtube_jobs[job_id].update({
            "status": "processing",
            "step": step,
            "progress": pct,
            "message": msg,
        })
    
    try:
        _youtube_jobs[job_id]["status"] = "processing"
        
        result = await process_youtube_video(
            url=url,
            progress_callback=progress_callback,
            speaker=speaker,
            category=category,
        )
        
        _youtube_jobs[job_id].update({
            "status": "complete",
            "step": "complete",
            "progress": 100,
            "message": "Processing complete!",
            "video_id": result["video_id"],
            "result": result,
        })
        
        logger.info(f"✅ YouTube job {job_id} complete: video_id={result['video_id']}")
        
    except Exception as e:
        logger.error(f"❌ YouTube job {job_id} failed: {e}", exc_info=True)
        _youtube_jobs[job_id].update({
            "status": "error",
            "step": "error",
            "progress": 0,
            "message": str(e),
            "error": str(e),
        })


@router.get("/admin/youtube/{job_id}")
async def get_youtube_job_status(job_id: str):
    """Get the status of a YouTube processing job."""
    if job_id not in _youtube_jobs:
        raise HTTPException(404, "Job not found")
    return _youtube_jobs[job_id]


@router.get("/admin/youtube")
async def list_youtube_jobs():
    """List all YouTube processing jobs (most recent first)."""
    jobs = sorted(
        _youtube_jobs.values(),
        key=lambda j: j.get("created_at", ""),
        reverse=True
    )
    return {"jobs": jobs}


@router.delete("/admin/videos/{video_id}")
async def delete_video(video_id: str):
    """Admin: Delete a video and its content."""
    from data.videos_content import delete_video_content
    
    video = get_video_detail(video_id, "hi")
    if not video:
        raise HTTPException(404, "Video not found")
    
    success = delete_video_content(video_id)
    if not success:
        raise HTTPException(500, "Failed to delete video")
    
    logger.info(f"🗑️ Deleted video: {video_id}")
    return {"status": "ok", "message": f"Video {video_id} deleted"}


@router.put("/admin/videos/{video_id}/url")
async def set_video_url(video_id: str, request: UpdateVideoUrlRequest):
    """Admin: Set/update the YouTube URL for a video."""
    video = get_video_detail(video_id, "hi")
    if not video:
        raise HTTPException(404, "Video not found")
    
    success = update_video_content(video_id, {"video_url": request.video_url})
    if not success:
        raise HTTPException(500, "Failed to update video URL")
    
    logger.info(f"Updated video URL for {video_id}: {request.video_url}")
    return {"status": "ok", "video_id": video_id, "video_url": request.video_url}


@router.post("/admin/videos/{video_id}/regenerate")
async def regenerate_video_content(video_id: str, background_tasks: BackgroundTasks):
    """Admin: Regenerate summary & explanation for a video."""
    video = get_video_detail(video_id, "hi")
    if not video:
        raise HTTPException(404, "Video not found")
    
    transcript_text = video.get("transcript", "")
    if not transcript_text:
        raise HTTPException(400, "Video has no transcript to generate from")
    
    async def _regenerate():
        try:
            summary_hi = await llm_engine.generate_summary(transcript_text, "hi")
            summary_en = await llm_engine.generate_summary(transcript_text, "en")
            explanation_hi = await llm_engine.generate_explanation(transcript_text, "hi")
            explanation_en = await llm_engine.generate_explanation(transcript_text, "en")
            
            update_video_content(video_id, {
                "summary_hi": summary_hi,
                "summary_en": summary_en,
                "explanation_hi": explanation_hi,
                "explanation_en": explanation_en,
            })
            logger.info(f"✅ Regenerated content for {video_id}")
        except Exception as e:
            logger.error(f"❌ Regeneration failed for {video_id}: {e}")
    
    background_tasks.add_task(_regenerate)
    return {"status": "ok", "message": "Regeneration started in background"}



# ========== Health Check ==========

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "voice_cloning_enabled": getattr(settings, 'USE_VOICE_CLONING', False)
    }

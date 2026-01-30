"""
Divya Vaani AI - Main API Routes
Unified API for upload, transcript, summary, explanation, chat, and speech.
"""
import os
import uuid
import logging
from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from config import settings
from data.schema import (
    UploadResponse, TranscriptResponse, ChatRequest, ChatResponse,
    SourceType, TTSRequest, TTSResponse
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
    
    # Save uploaded file
    file_path = settings.UPLOAD_DIR / f"{file_id}{file_ext}"
    
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        file_size_mb = len(content) / (1024 * 1024)
        logger.info(f"📁 Uploaded: {file.filename} ({file_size_mb:.1f} MB)")
        
    except Exception as e:
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
async def chat(request: ChatRequest):
    """
    Ask a question - answers come from uploaded spiritual discourses.
    
    The system searches through transcribed pravachans to find relevant
    spiritual guidance for the user's question, then provides wisdom
    from Maharaj Ji's teachings.
    """
    question = request.question.strip()
    language = request.language if request.language in ["hi", "en"] else "hi"
    
    if not question:
        raise HTTPException(400, "Question cannot be empty")
    
    # Always search transcripts if any exist
    if request.transcript_id or rag_engine.has_transcripts():
        # Expand question with spiritual keywords for better semantic search
        expanded_query = _expand_question_for_search(question)
        
        # Search with expanded query and get more chunks
        chunks = rag_engine.search_transcripts(
            expanded_query, 
            transcript_id=request.transcript_id,
            top_k=10  # Get more chunks for better context
        )
        
        # If no results with expanded query, try original question
        if not chunks:
            chunks = rag_engine.search_transcripts(
                question, 
                transcript_id=request.transcript_id,
                top_k=10
            )
        
        if chunks:
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
            
            # Generate audio for answer (using cloned voice)
            audio_url = await tts_engine.generate_speech_async(answer, language, mode="clone")
            
            return ChatResponse(
                answer=answer,
                source_type=SourceType.PRAVACHAN,
                source_reference=f"Based on {len(chunks)} segments from the discourse",
                audio_url=audio_url
            )
    
    # TODO: Bhagavad Gita fallback (deferred)
    
    # Not found response
    not_found = await llm_engine.generate_not_found(language)
    audio_url = await tts_engine.generate_speech_async(not_found, language, mode="clone")
    
    return ChatResponse(
        answer=not_found,
        source_type=SourceType.NOT_FOUND,
        source_reference="",
        audio_url=audio_url
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
            except:
                pass


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
    path = settings.AUDIO_DIR / filename
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

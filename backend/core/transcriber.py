"""
Divya Vaani AI - Simple Working Transcriber
Uses ONLY Groq API - proven to work, no GPU/download issues.
Supports large files by chunking audio before transcription.
Includes Hindi spell-check/grammar correction post-processing.
"""
import json
import logging
import time
import os
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import httpx

from config import settings
from data.schema import TranscriptChunk, Transcript

logger = logging.getLogger(__name__)

# Max file size for Groq API (25MB, use 15MB to be safer for stability)
MAX_FILE_SIZE_MB = 15
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Max chunk duration in milliseconds (5 minutes - smaller chunks = more reliable)
MAX_CHUNK_DURATION_MS = 5 * 60 * 1000

# Delay between API calls to avoid rate limiting/overload (seconds)
CHUNK_DELAY_SECONDS = 3


PROMPT = "प्रेमानंद महाराज प्रवचन। भगवद्गीता, श्रीकृष्ण, कर्म, धर्म, भक्ति।"


# ========== Hindi Spell Check / Grammar Correction ==========

async def _correct_hindi_text(text: str) -> str:
    """
    Correct Hindi spelling and grammar mistakes using Gemini.
    Keeps the original words/meaning intact, only fixes spelling errors.
    """
    if not text or len(text.strip()) < 10:
        return text
    
    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        prompt = f"""You are a Hindi spelling and grammar corrector for spiritual discourse transcriptions.

TASK: Fix ONLY spelling mistakes and grammar errors in the following Hindi text.

STRICT RULES:
1. DO NOT change any words - only fix spelling of existing words
2. DO NOT add or remove any words
3. DO NOT change the meaning
4. DO NOT translate anything
5. Fix common Whisper transcription errors like:
   - "शहिष्णू" → "सहिष्णु" (patience)
   - "सहरा" → "सहारा" (support)
   - "भघ्वान" → "भगवान" (God)
   - "तास्तितिक" → "तात्विक" (philosophical)
   - "प्रवचन" spelling errors
   - Missing मात्राएँ (vowel marks)
   - Wrong conjuncts (संयुक्त अक्षर)
6. Keep Sanskrit shlokas and mantras exactly as they are
7. Keep proper nouns (names) as they are

INPUT TEXT:
{text}

OUTPUT: Return ONLY the corrected text, nothing else. No explanations."""

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model='gemini-2.0-flash', contents=prompt
            )
        )
        
        corrected = response.text.strip()
        
        # Basic validation - if output is drastically different, use original
        if len(corrected) < len(text) * 0.5 or len(corrected) > len(text) * 1.5:
            logger.warning("⚠️ Spell-check output too different, using original")
            return text
        
        return corrected
        
    except Exception as e:
        logger.warning(f"⚠️ Hindi spell-check failed: {e}, using original text")
        return text


async def correct_transcript_chunks(chunks: List['TranscriptChunk'], progress_callback=None) -> List['TranscriptChunk']:
    """
    Correct spelling/grammar in all transcript chunks.
    Processes in batches to be efficient.
    """
    if not chunks:
        return chunks
    
    logger.info(f"📝 Starting Hindi spell-check for {len(chunks)} chunks...")
    
    # Process chunks in batches of 10 for efficiency
    batch_size = 10
    corrected_chunks = []
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        
        # Combine batch texts with separators
        combined_text = "\n---CHUNK_SEPARATOR---\n".join([c.text for c in batch])
        
        if progress_callback:
            progress_callback(i, len(chunks), f"Spell-checking chunks {i+1}-{min(i+batch_size, len(chunks))}...")
        
        # Correct combined text
        corrected_combined = await _correct_hindi_text(combined_text)
        
        # Split back into individual chunks
        corrected_texts = corrected_combined.split("\n---CHUNK_SEPARATOR---\n")
        
        # If split failed, use original texts
        if len(corrected_texts) != len(batch):
            logger.warning(f"⚠️ Batch split mismatch, using original texts for batch {i//batch_size + 1}")
            corrected_texts = [c.text for c in batch]
        
        # Create corrected chunks
        for j, chunk in enumerate(batch):
            corrected_text = corrected_texts[j].strip() if j < len(corrected_texts) else chunk.text
            corrected_chunks.append(TranscriptChunk(
                id=chunk.id,
                text=corrected_text,
                start_time=chunk.start_time,
                end_time=chunk.end_time
            ))
    
    logger.info(f"✅ Hindi spell-check complete for {len(corrected_chunks)} chunks")
    return corrected_chunks


def _get_file_size_mb(file_path: Path) -> float:
    """Get file size in megabytes."""
    return os.path.getsize(file_path) / (1024 * 1024)


def _split_audio_file(file_path: Path, max_duration_ms: int = MAX_CHUNK_DURATION_MS) -> List[Tuple[Path, float]]:
    """
    Split large audio file into smaller chunks.
    Returns list of (chunk_path, start_time_seconds) tuples.
    """
    from pydub import AudioSegment
    
    logger.info(f"📦 Loading audio file for chunking: {file_path.name}")
    
    # Load audio file
    file_ext = file_path.suffix.lower()
    if file_ext == '.mp3':
        audio = AudioSegment.from_mp3(str(file_path))
    elif file_ext == '.wav':
        audio = AudioSegment.from_wav(str(file_path))
    elif file_ext == '.ogg':
        audio = AudioSegment.from_ogg(str(file_path))
    elif file_ext == '.flac':
        audio = AudioSegment.from_file(str(file_path), format='flac')
    elif file_ext in ['.mp4', '.m4a', '.webm']:
        audio = AudioSegment.from_file(str(file_path))
    else:
        audio = AudioSegment.from_file(str(file_path))
    
    total_duration_ms = len(audio)
    total_duration_s = total_duration_ms / 1000
    logger.info(f"📊 Audio duration: {total_duration_s/60:.1f} minutes ({total_duration_s:.0f}s)")
    
    # If audio is small enough, return as-is
    file_size_mb = _get_file_size_mb(file_path)
    if file_size_mb <= MAX_FILE_SIZE_MB and total_duration_ms <= max_duration_ms:
        logger.info(f"✅ File size ({file_size_mb:.1f}MB) is within limit, no chunking needed")
        return [(file_path, 0.0)]
    
    # Split into chunks
    chunks = []
    temp_dir = tempfile.mkdtemp(prefix="divya_vaani_chunks_")
    
    start_ms = 0
    chunk_index = 0
    
    while start_ms < total_duration_ms:
        end_ms = min(start_ms + max_duration_ms, total_duration_ms)
        chunk_audio = audio[start_ms:end_ms]
        
        # Export chunk as mp3 (good compression)
        chunk_path = Path(temp_dir) / f"chunk_{chunk_index}.mp3"
        chunk_audio.export(str(chunk_path), format="mp3", bitrate="128k")
        
        chunk_size_mb = _get_file_size_mb(chunk_path)
        logger.info(f"📦 Chunk {chunk_index + 1}: {start_ms/1000:.0f}s - {end_ms/1000:.0f}s ({chunk_size_mb:.1f}MB)")
        
        # If chunk is still too large, split further
        if chunk_size_mb > MAX_FILE_SIZE_MB:
            logger.warning(f"⚠️ Chunk still too large ({chunk_size_mb:.1f}MB), splitting further...")
            # Recursively split with smaller duration
            sub_chunks = _split_audio_file(chunk_path, max_duration_ms // 2)
            for sub_path, sub_offset in sub_chunks:
                chunks.append((sub_path, (start_ms / 1000) + sub_offset))
            chunk_path.unlink()  # Remove oversized chunk
        else:
            chunks.append((chunk_path, start_ms / 1000))
        
        start_ms = end_ms
        chunk_index += 1
    
    logger.info(f"✅ Split into {len(chunks)} chunks")
    return chunks


async def _transcribe_single_chunk(file_path: Path, time_offset: float = 0.0, max_retries: int = 8) -> Tuple[List[dict], float]:
    """Transcribe a single audio chunk via Groq API with retry logic."""
    import asyncio
    
    last_error = None
    file_size_mb = _get_file_size_mb(file_path)
    logger.info(f"   📤 Uploading {file_size_mb:.1f}MB to Groq Whisper API...")
    
    for attempt in range(max_retries):
        try:
            # Use very long timeout for stability (5 min read, 2 min connect)
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=120.0, read=300.0)) as client:
                with open(file_path, "rb") as f:
                    logger.info(f"   ⏳ Waiting for Groq API response (attempt {attempt + 1}/{max_retries})...")
                    response = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        files={"file": (file_path.name, f, "audio/mpeg")},
                        data={
                            "model": "whisper-large-v3",
                            "response_format": "verbose_json",
                            "language": "hi",
                            "temperature": 0.0,
                            "prompt": PROMPT
                        }
                    )
            
            logger.info(f"   📥 Got response: {response.status_code}")
            
            # Handle rate limiting (429)
            if response.status_code == 429:
                wait_time = 30  # Wait 30 seconds for rate limit
                logger.warning(f"⚠️ Rate limited (429), waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
                last_error = "Rate limited"
                continue
            
            # Retry on 5xx server errors with exponential backoff
            if response.status_code >= 500:
                wait_time = (attempt + 1) * 15  # 15s, 30s, 45s, 60s, 75s
                logger.warning(f"⚠️ Server error {response.status_code}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                last_error = f"Server error: {response.status_code}"
                continue
            
            if response.status_code != 200:
                logger.error(f"❌ API Error: {response.text[:500]}")
                raise ValueError(f"Transcription failed: {response.status_code}")
            
            result = response.json()
            logger.info(f"   ✅ Transcribed {len(result.get('segments', []))} segments")
            
            # Adjust timestamps with offset
            segments = []
            for seg in result.get("segments", []):
                segments.append({
                    "text": seg.get("text", "").strip(),
                    "start": seg.get("start", 0.0) + time_offset,
                    "end": seg.get("end", 0.0) + time_offset
                })
            
            # Fallback if no segments
            if not segments and result.get("text"):
                duration = result.get("duration", 0.0)
                segments.append({
                    "text": result["text"].strip(),
                    "start": time_offset,
                    "end": time_offset + duration
                })
            
            chunk_duration = result.get("duration", 0.0)
            return segments, chunk_duration
            
        except httpx.TimeoutException as e:
            wait_time = min(60, (attempt + 1) * 15)  # 15s, 30s, 45s, 60s max
            logger.error(f"❌ Timeout! Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
            last_error = f"Timeout: {str(e)}"
            continue
        except httpx.ReadError as e:
            wait_time = min(60, (attempt + 1) * 15)  # Read errors need longer waits
            logger.error(f"❌ ReadError (connection dropped): Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
            last_error = f"ReadError: {str(e)}"
            continue
        except httpx.ConnectError as e:
            wait_time = min(45, (attempt + 1) * 10)
            logger.error(f"❌ Connection error: {e}. Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            last_error = f"Connection error: {str(e)}"
            continue
        except ValueError:
            raise  # Don't retry client errors (4xx)
        except Exception as e:
            wait_time = min(45, (attempt + 1) * 10)
            logger.error(f"❌ Error: {type(e).__name__}: {e}, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
            last_error = str(e)
            continue
    
    # All retries exhausted
    logger.error(f"❌ Transcription failed after {max_retries} attempts: {last_error}")
    raise ValueError(f"Transcription failed after {max_retries} attempts: {last_error}")


async def transcribe_audio(file_id: str, file_path: Path, filename: str, progress_callback=None) -> Transcript:
    """Transcribe audio file, handling large files by chunking."""
    start = time.time()
    logger.info(f"🎤 Starting transcription: {filename}")
    
    file_size_mb = _get_file_size_mb(file_path)
    logger.info(f"📊 File size: {file_size_mb:.1f} MB")
    
    if progress_callback:
        progress_callback(0, 1, "Preparing audio...")
    
    # Check if we need to split the file
    chunk_files = []
    temp_files_to_cleanup = []
    
    if file_size_mb > MAX_FILE_SIZE_MB:
        logger.info(f"📦 File too large ({file_size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB), splitting...")
        if progress_callback:
            progress_callback(0, 1, "Splitting large audio file...")
        chunk_files = _split_audio_file(file_path)
        # Mark temp files for cleanup (but not the original)
        temp_files_to_cleanup = [p for p, _ in chunk_files if p != file_path]
    else:
        chunk_files = [(file_path, 0.0)]
    
    # Transcribe all chunks
    all_segments = []
    total_duration = 0.0
    
    try:
        for i, (chunk_path, time_offset) in enumerate(chunk_files):
            if progress_callback:
                progress_callback(i, len(chunk_files), f"Transcribing chunk {i+1}/{len(chunk_files)}...")
            
            logger.info(f"📡 Sending chunk {i+1}/{len(chunk_files)} to Groq API...")
            segments, chunk_duration = await _transcribe_single_chunk(chunk_path, time_offset)
            all_segments.extend(segments)
            
            # Update total duration (use max end time)
            if segments:
                total_duration = max(total_duration, segments[-1]["end"])
            
            # Add delay between chunks to avoid rate limiting and API overload
            if i < len(chunk_files) - 1:  # Don't delay after the last chunk
                logger.info(f"⏳ Waiting {CHUNK_DELAY_SECONDS}s before next chunk to avoid API overload...")
                await asyncio.sleep(CHUNK_DELAY_SECONDS)
        
        logger.info(f"✅ Got {len(all_segments)} segments from {len(chunk_files)} chunks")
        
    finally:
        # Cleanup temp files
        for temp_path in temp_files_to_cleanup:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
        # Also try to cleanup temp directory
        for temp_path in temp_files_to_cleanup:
            try:
                temp_dir = temp_path.parent
                if temp_dir.exists() and temp_dir.name.startswith("divya_vaani_chunks_"):
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    break
            except Exception:
                pass
    
    # Build transcript chunks
    chunks = []
    for i, seg in enumerate(all_segments):
        text = seg.get("text", "").strip()
        if text:
            chunks.append(TranscriptChunk(
                id=f"{file_id}_{i}",
                text=text,
                start_time=seg.get("start", 0.0),
                end_time=seg.get("end", 0.0)
            ))
    
    # Apply Hindi spell-check/grammar correction
    if chunks:
        if progress_callback:
            progress_callback(0, 1, "Correcting Hindi spelling...")
        
        try:
            chunks = await correct_transcript_chunks(chunks, progress_callback)
            logger.info("✅ Hindi spell-check applied successfully")
        except Exception as e:
            logger.warning(f"⚠️ Hindi spell-check failed, using original: {e}")
    
    full_text = " ".join([c.text for c in chunks])
    
    transcript = Transcript(
        id=file_id,
        filename=filename,
        title=full_text[:50] + "..." if len(full_text) > 50 else full_text,
        chunks=chunks,
        duration=total_duration,
        created_at=datetime.now(),
        full_text=full_text
    )
    
    _save_transcript(transcript)
    
    elapsed = time.time() - start
    logger.info(f"✅ Done: {len(chunks)} segments, {total_duration:.0f}s audio in {elapsed:.1f}s ({total_duration/elapsed:.1f}x)")
    
    if progress_callback:
        progress_callback(1, 1, "Complete!")
    
    return transcript


async def transcribe_voice(file_path: Path, language: str = None) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(file_path, "rb") as f:
            # Detect MIME type from file extension
            suffix = file_path.suffix.lower()
            mime_map = {".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
                        ".wav": "audio/wav", ".m4a": "audio/mp4", ".mp4": "audio/mp4"}
            mime_type = mime_map.get(suffix, "audio/webm")
            
            data = {"model": "whisper-large-v3", "response_format": "text"}
            # Only set language if explicitly specified; otherwise let Whisper auto-detect
            if language and language != "auto":
                data["language"] = language
            
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                files={"file": (file_path.name, f, mime_type)},
                data=data,
            )
    if response.status_code != 200:
        raise ValueError(f"Failed: {response.text}")
    return response.text.strip()


def _save_transcript(t: Transcript):
    path = settings.TRANSCRIPTS_DIR / f"{t.id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "id": t.id, "filename": t.filename, "title": t.title,
            "duration": t.duration, "full_text": t.full_text,
            "created_at": t.created_at.isoformat(),
            "chunks": [c.model_dump() for c in t.chunks]
        }, f, ensure_ascii=False, indent=2)


def load_transcript(transcript_id: str) -> Transcript | None:
    path = settings.TRANSCRIPTS_DIR / f"{transcript_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    chunks = [TranscriptChunk(**c) for c in data.get("chunks", [])]
    return Transcript(
        id=data["id"], filename=data["filename"], title=data["title"],
        duration=data["duration"], created_at=datetime.fromisoformat(data["created_at"]),
        chunks=chunks, full_text=data.get("full_text", "")
    )


def list_transcripts() -> List[dict]:
    transcripts = []
    for path in settings.TRANSCRIPTS_DIR.glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            transcripts.append({
                "id": data["id"], "title": data["title"], "filename": data["filename"],
                "duration": data["duration"], "created_at": data["created_at"]
            })
        except Exception:
            pass
    transcripts.sort(key=lambda x: x["created_at"], reverse=True)
    return transcripts

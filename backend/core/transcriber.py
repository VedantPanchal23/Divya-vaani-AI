"""
Divya Vaani AI - Simple Working Transcriber
Uses ONLY Groq API - proven to work, no GPU/download issues.
Supports large files by chunking audio before transcription.
"""
import json
import logging
import time
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import httpx

from config import settings

logger = logging.getLogger(__name__)

# Max file size for Groq API (25MB, use 20MB to be safe)
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Max chunk duration in milliseconds (10 minutes)
MAX_CHUNK_DURATION_MS = 10 * 60 * 1000


class TranscriptChunk:
    def __init__(self, id: str, text: str, start_time: float, end_time: float):
        self.id = id
        self.text = text
        self.start_time = start_time
        self.end_time = end_time
    
    def to_dict(self):
        return {"id": self.id, "text": self.text, "start_time": self.start_time, "end_time": self.end_time}


class Transcript:
    def __init__(self, id: str, filename: str, title: str, chunks: List[TranscriptChunk], 
                 duration: float, created_at: datetime, full_text: str = ""):
        self.id = id
        self.filename = filename
        self.title = title
        self.chunks = chunks
        self.duration = duration
        self.created_at = created_at
        self.full_text = full_text or " ".join([c.text for c in chunks])


PROMPT = "प्रेमानंद महाराज प्रवचन। भगवद्गीता, श्रीकृष्ण, कर्म, धर्म, भक्ति।"


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


async def _transcribe_single_chunk(file_path: Path, time_offset: float = 0.0) -> Tuple[List[dict], float]:
    """Transcribe a single audio chunk via Groq API."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(file_path, "rb") as f:
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
    
    if response.status_code != 200:
        logger.error(f"❌ API Error: {response.text[:500]}")
        raise ValueError(f"Transcription failed: {response.status_code}")
    
    result = response.json()
    
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
        
        logger.info(f"✅ Got {len(all_segments)} segments from {len(chunk_files)} chunks")
        
    finally:
        # Cleanup temp files
        for temp_path in temp_files_to_cleanup:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except:
                pass
        # Also try to cleanup temp directory
        for temp_path in temp_files_to_cleanup:
            try:
                temp_dir = temp_path.parent
                if temp_dir.exists() and temp_dir.name.startswith("divya_vaani_chunks_"):
                    import shutil
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    break
            except:
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


async def transcribe_voice(file_path: Path) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(file_path, "rb") as f:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                files={"file": (file_path.name, f, "audio/mpeg")},
                data={"model": "whisper-large-v3", "response_format": "text", "language": "hi"}
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
            "chunks": [c.to_dict() for c in t.chunks]
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
        except:
            pass
    transcripts.sort(key=lambda x: x["created_at"], reverse=True)
    return transcripts

"""
Divya Vaani AI - Simple Working Transcriber
Uses ONLY Groq API - proven to work, no GPU/download issues.
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import httpx

from config import settings

logger = logging.getLogger(__name__)


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


async def transcribe_audio(file_id: str, file_path: Path, filename: str, progress_callback=None) -> Transcript:
    """Simple Groq API transcription - reliable and fast."""
    start = time.time()
    logger.info(f"🎤 Starting transcription: {filename}")
    
    if progress_callback:
        progress_callback(0, 1, "Transcribing...")
    
    # Call Groq API
    async with httpx.AsyncClient(timeout=300.0) as client:
        with open(file_path, "rb") as f:
            logger.info("📡 Sending to Groq API...")
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
    logger.info("✅ Got response from Groq")
    
    # Parse segments
    chunks = []
    for i, seg in enumerate(result.get("segments", [])):
        text = seg.get("text", "").strip()
        if text:
            chunks.append(TranscriptChunk(
                id=f"{file_id}_{i}",
                text=text,
                start_time=seg.get("start", 0.0),
                end_time=seg.get("end", 0.0)
            ))
    
    # Fallback
    if not chunks and result.get("text"):
        chunks.append(TranscriptChunk(file_id + "_0", result["text"].strip(), 0.0, result.get("duration", 0.0)))
    
    duration = result.get("duration", chunks[-1].end_time if chunks else 0)
    full_text = " ".join([c.text for c in chunks])
    
    transcript = Transcript(
        id=file_id,
        filename=filename,
        title=full_text[:50] + "..." if len(full_text) > 50 else full_text,
        chunks=chunks,
        duration=duration,
        created_at=datetime.now(),
        full_text=full_text
    )
    
    _save_transcript(transcript)
    
    elapsed = time.time() - start
    logger.info(f"✅ Done: {len(chunks)} segments, {duration:.0f}s audio in {elapsed:.1f}s ({duration/elapsed:.1f}x)")
    
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

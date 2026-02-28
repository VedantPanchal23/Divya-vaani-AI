"""
Divya Vaani AI - YouTube Processing Pipeline
Downloads audio from YouTube, transcribes, indexes, generates summaries.
"""
import os
import re
import uuid
import logging
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

import yt_dlp

from config import settings
from core.transcriber import transcribe_audio
from core.rag_engine import index_transcript
from core.llm_engine import generate_summary, generate_explanation
from data.videos_content import add_video_content, VideoContent

logger = logging.getLogger(__name__)

# Download directory for YouTube audio
YOUTUBE_DOWNLOAD_DIR = settings.DATA_DIR / "youtube_downloads"
YOUTUBE_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_info(url: str) -> dict:
    """Get video metadata without downloading."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "channel": info.get("channel", info.get("uploader", "")),
            "description": info.get("description", "")[:500],
            "youtube_id": info.get("id", ""),
        }


def download_youtube_audio(url: str, output_dir: Path = None) -> tuple[Path, dict]:
    """
    Download audio from YouTube URL.
    Returns: (audio_file_path, video_info_dict)
    """
    if output_dir is None:
        output_dir = YOUTUBE_DOWNLOAD_DIR
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_id = str(uuid.uuid4())[:12]
    output_path = output_dir / f"{file_id}.mp3"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_dir / f"{file_id}.%(ext)s"),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'quiet': True,
        'no_warnings': True,
    }
    
    logger.info(f"📥 Downloading audio from YouTube: {url}")
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    
    # Find the downloaded file (yt-dlp may change the extension)
    possible_paths = [
        output_dir / f"{file_id}.mp3",
        output_dir / f"{file_id}.m4a",
        output_dir / f"{file_id}.webm",
        output_dir / f"{file_id}.opus",
    ]
    
    actual_path = None
    for p in possible_paths:
        if p.exists():
            actual_path = p
            break
    
    if actual_path is None:
        # Search for any file with our ID prefix
        for f in output_dir.glob(f"{file_id}.*"):
            actual_path = f
            break
    
    if actual_path is None:
        raise FileNotFoundError(f"Downloaded audio file not found for {file_id}")
    
    file_size_mb = os.path.getsize(actual_path) / (1024 * 1024)
    logger.info(f"✅ Downloaded: {actual_path.name} ({file_size_mb:.1f} MB)")
    
    video_info = {
        "title": info.get("title", "Untitled"),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail", ""),
        "channel": info.get("channel", info.get("uploader", "")),
        "description": info.get("description", "")[:500],
        "youtube_id": info.get("id", ""),
        "youtube_url": url,
    }
    
    return actual_path, video_info


async def process_youtube_video(
    url: str,
    progress_callback: Optional[Callable] = None,
    speaker: str = "Maharaj Ji",
    category: str = "pravachan",
) -> dict:
    """
    Full pipeline: YouTube URL → download → transcribe → index → summarize → save
    
    Args:
        url: YouTube URL
        progress_callback: fn(step, progress_pct, message) for status updates
        speaker: Speaker name
        category: Video category
    
    Returns: dict with video_id and all generated data
    """
    video_id = str(uuid.uuid4())[:12]
    
    def update(step: str, pct: int, msg: str):
        if progress_callback:
            progress_callback(step, pct, msg)
        logger.info(f"[{video_id}] {step}: {msg} ({pct}%)")
    
    try:
        # ===== Step 1: Download Audio =====
        update("downloading", 5, "Downloading audio from YouTube...")
        
        audio_path, video_info = await asyncio.get_event_loop().run_in_executor(
            None, lambda: download_youtube_audio(url)
        )
        
        youtube_url = video_info["youtube_url"]
        yt_id = video_info["youtube_id"]
        
        update("downloading", 15, f"Downloaded: {video_info['title'][:50]}...")
        
        # ===== Step 2: Transcribe =====
        update("transcribing", 20, "Transcribing audio with Whisper...")
        
        def transcription_progress(current, total, msg):
            pct = 20 + int((current / max(total, 1)) * 30)
            update("transcribing", pct, msg)
        
        transcript = await transcribe_audio(
            video_id, audio_path, video_info["title"], transcription_progress
        )
        
        update("transcribing", 50, f"Transcribed {len(transcript.chunks)} segments")
        
        # ===== Step 3: Index for RAG =====
        update("indexing", 55, "Indexing transcript for Q&A search...")
        
        try:
            index_transcript(transcript)
            update("indexing", 60, "Indexed for semantic search")
        except Exception as e:
            logger.warning(f"⚠️ Indexing failed (non-fatal): {e}")
            update("indexing", 60, "Indexing partially failed (search may be limited)")
        
        # ===== Step 4: Generate Summary (both languages) =====
        update("summarizing", 62, "Generating Hindi summary...")
        summary_hi = ""
        summary_en = ""
        
        try:
            summary_hi = await generate_summary(transcript.full_text, "hi")
            update("summarizing", 70, "Generating English summary...")
            summary_en = await generate_summary(transcript.full_text, "en")
        except Exception as e:
            logger.warning(f"⚠️ Summary generation failed: {e}")
            update("summarizing", 75, "Summary generation failed (can retry later)")
        
        # ===== Step 5: Generate Explanation (both languages) =====
        update("explaining", 78, "Generating Hindi explanation...")
        explanation_hi = ""
        explanation_en = ""
        
        try:
            explanation_hi = await generate_explanation(transcript.full_text, "hi")
            update("explaining", 85, "Generating English explanation...")
            explanation_en = await generate_explanation(transcript.full_text, "en")
        except Exception as e:
            logger.warning(f"⚠️ Explanation generation failed: {e}")
            update("explaining", 90, "Explanation generation failed (can retry later)")
        
        # ===== Step 6: Generate titles from content =====
        update("finalizing", 92, "Generating title...")
        
        # Use first 60 chars of Hindi transcript as title_hi
        first_text = transcript.full_text[:100].strip()
        if len(first_text) > 60:
            cut = first_text[:60].rfind(' ')
            if cut > 20:
                first_text = first_text[:cut]
            else:
                first_text = first_text[:60]
        title_hi = first_text + "..." if len(transcript.full_text) > 60 else first_text
        
        # Use YouTube title as English title  
        title_en = video_info["title"]
        
        # ===== Step 7: Save to videos_content.json =====
        update("finalizing", 95, "Saving video content...")
        
        # Build transcript chunks in the format used by the app
        chunk_data = [
            {"text": c.text, "start": c.start_time, "end": c.end_time}
            for c in transcript.chunks
        ]
        
        video_content = VideoContent(
            id=video_id,
            title=title_en,
            title_hi=title_hi,
            description=video_info["description"][:200] if video_info["description"] else f"Spiritual discourse by {speaker}",
            description_hi=f"{speaker} द्वारा आध्यात्मिक प्रवचन",
            thumbnail=f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg" if yt_id else None,
            video_url=youtube_url,
            duration=transcript.duration,
            transcript=transcript.full_text,
            transcript_chunks=chunk_data,
            summary_hi=summary_hi,
            summary_en=summary_en,
            explanation_hi=explanation_hi,
            explanation_en=explanation_en,
            category=category,
            speaker=speaker,
            tags=f"{speaker} प्रवचन अध्यात्म spiritual discourse",
            created_at=datetime.now().isoformat(),
        )
        
        add_video_content(video_content)
        
        # Cleanup downloaded audio
        try:
            if audio_path.exists():
                audio_path.unlink()
        except Exception:
            pass
        
        update("complete", 100, "Processing complete!")
        
        return {
            "video_id": video_id,
            "title": title_en,
            "title_hi": title_hi,
            "duration": transcript.duration,
            "chunks_count": len(transcript.chunks),
            "has_summary": bool(summary_hi),
            "has_explanation": bool(explanation_hi),
            "youtube_url": youtube_url,
            "youtube_id": yt_id,
        }
        
    except Exception as e:
        update("error", 0, f"Failed: {str(e)}")
        logger.error(f"❌ YouTube processing failed for {url}: {e}", exc_info=True)
        raise

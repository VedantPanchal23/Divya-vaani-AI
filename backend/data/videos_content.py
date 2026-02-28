"""
Pre-processed Video Content Store
Contains pre-computed transcripts, summaries, and explanations for spiritual videos.
Q&A is generated at runtime using RAG.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

# In-memory cache to avoid reloading JSON from disk on every API call
_videos_cache: Optional[Dict[str, 'VideoContent']] = None
_cache_mtime: float = 0  # Last modified time of the JSON file

class VideoContent(BaseModel):
    """Pre-processed video content with transcript, summary, and explanation."""
    id: str
    title: str
    title_hi: str  # Hindi title
    description: str
    description_hi: str  # Hindi description
    thumbnail: str  # Thumbnail URL/path
    video_url: Optional[str] = None  # Original video URL if available
    duration: float  # Duration in seconds
    
    # Pre-computed content
    transcript: str
    transcript_chunks: List[Dict[str, Any]]  # [{id, text, start_time, end_time}]
    summary_hi: str
    summary_en: str
    explanation_hi: str
    explanation_en: str
    
    # Audio URLs for pre-generated TTS
    summary_audio_hi: Optional[str] = None
    summary_audio_en: Optional[str] = None
    explanation_audio_hi: Optional[str] = None
    explanation_audio_en: Optional[str] = None
    
    # Metadata
    created_at: str
    category: str = "pravachan"  # pravachan, bhajan, discourse, etc.
    speaker: str = "Maharaj Ji"
    tags: str = ""  # Space-separated tags string


# Video content storage path
VIDEOS_CONTENT_FILE = settings.DATA_DIR / "videos_content.json"


def _load_videos_content() -> Dict[str, VideoContent]:
    """Load all pre-processed video content with caching."""
    global _videos_cache, _cache_mtime
    
    if not VIDEOS_CONTENT_FILE.exists():
        _videos_cache = {}
        return {}
    
    # Check if file has been modified since last load
    current_mtime = VIDEOS_CONTENT_FILE.stat().st_mtime
    if _videos_cache is not None and current_mtime == _cache_mtime:
        return _videos_cache
    
    try:
        with open(VIDEOS_CONTENT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        _videos_cache = {vid_id: VideoContent(**content) for vid_id, content in data.items()}
        _cache_mtime = current_mtime
        return _videos_cache
    except Exception as e:
        logger.error(f"Failed to load videos content: {e}")
        return {}


def _save_videos_content(videos: Dict[str, VideoContent]):
    """Save all video content and invalidate cache."""
    global _videos_cache, _cache_mtime
    try:
        data = {vid_id: content.model_dump() for vid_id, content in videos.items()}
        with open(VIDEOS_CONTENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Update cache immediately
        _videos_cache = videos
        _cache_mtime = VIDEOS_CONTENT_FILE.stat().st_mtime
    except Exception as e:
        logger.error(f"Failed to save videos content: {e}")


def get_all_videos() -> List[Dict[str, Any]]:
    """Get list of all videos with basic info (for cards)."""
    videos = _load_videos_content()
    
    return [
        {
            "id": vid.id,
            "title": vid.title,
            "title_hi": vid.title_hi,
            "description": vid.description,
            "description_hi": vid.description_hi,
            "thumbnail": vid.thumbnail,
            "video_url": vid.video_url,
            "duration": vid.duration,
            "category": vid.category,
            "speaker": vid.speaker,
            "tags": vid.tags,
            "created_at": vid.created_at
        }
        for vid in videos.values()
    ]


def get_video_detail(video_id: str, language: str = "hi") -> Optional[Dict[str, Any]]:
    """Get full video content for detail view. Returns both language variants."""
    videos = _load_videos_content()
    
    if video_id not in videos:
        return None
    
    vid = videos[video_id]
    
    return {
        "id": vid.id,
        "title": vid.title if language == "en" else vid.title_hi,
        "title_hi": vid.title_hi,
        "title_en": vid.title,
        "description": vid.description if language == "en" else vid.description_hi,
        "description_hi": vid.description_hi,
        "description_en": vid.description,
        "thumbnail": vid.thumbnail,
        "video_url": vid.video_url,
        "duration": vid.duration,
        "category": vid.category,
        "speaker": vid.speaker,
        "tags": vid.tags,
        
        # Full content - always include both languages
        "transcript": vid.transcript,
        "transcript_chunks": vid.transcript_chunks,
        "summary": vid.summary_en if language == "en" else vid.summary_hi,
        "summary_hi": vid.summary_hi,
        "summary_en": vid.summary_en,
        "explanation": vid.explanation_en if language == "en" else vid.explanation_hi,
        "explanation_hi": vid.explanation_hi,
        "explanation_en": vid.explanation_en,
        
        # Audio
        "summary_audio": vid.summary_audio_en if language == "en" else vid.summary_audio_hi,
        "summary_audio_hi": vid.summary_audio_hi,
        "summary_audio_en": vid.summary_audio_en,
        "explanation_audio": vid.explanation_audio_en if language == "en" else vid.explanation_audio_hi,
        "explanation_audio_hi": vid.explanation_audio_hi,
        "explanation_audio_en": vid.explanation_audio_en,
        
        "created_at": vid.created_at,
        "status": "complete"
    }


def add_video_content(content: VideoContent) -> bool:
    """Add new pre-processed video content."""
    videos = _load_videos_content()
    videos[content.id] = content
    _save_videos_content(videos)
    logger.info(f"✅ Added video content: {content.id}")
    return True


def update_video_content(video_id: str, updates: Dict[str, Any]) -> bool:
    """Update existing video content."""
    videos = _load_videos_content()
    
    if video_id not in videos:
        return False
    
    vid_dict = videos[video_id].model_dump()
    vid_dict.update(updates)
    videos[video_id] = VideoContent(**vid_dict)
    _save_videos_content(videos)
    return True


def delete_video_content(video_id: str) -> bool:
    """Delete video content."""
    videos = _load_videos_content()
    
    if video_id not in videos:
        return False
    
    del videos[video_id]
    _save_videos_content(videos)
    return True


def migrate_from_transcripts():
    """
    Migrate existing transcript files to the new video content format.
    Deduplicates by filename - keeps the version with most chunks.
    """
    import os
    import re
    from collections import defaultdict
    
    transcript_dir = settings.TRANSCRIPT_DIR
    if not transcript_dir.exists():
        logger.warning("No transcripts directory found")
        return
    
    # Load all transcripts and group by filename for deduplication
    by_filename = defaultdict(list)
    
    for transcript_file in transcript_dir.glob("*.json"):
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            filename = data.get("filename", transcript_file.stem)
            by_filename[filename].append(data)
        except Exception as e:
            logger.error(f"Failed to load {transcript_file}: {e}")
    
    # Deduplicate: keep version with most chunks per filename
    unique_transcripts = []
    for filename, versions in by_filename.items():
        versions.sort(key=lambda v: len(v.get("chunks", [])), reverse=True)
        unique_transcripts.append(versions[0])
    
    videos = _load_videos_content()
    migrated = 0
    
    for data in unique_transcripts:
        video_id = data.get("id", "unknown")
        
        if video_id in videos:
            # Check if existing entry has broken title (LLM output preamble)
            existing = videos[video_id]
            if existing.title.startswith("Here is") or "paragraph" in existing.title.lower():
                # Fix broken title - fall through to re-create
                logger.info(f"Fixing broken title for: {video_id}")
            else:
                continue  # Already migrated properly
        
        # Create clean title from filename
        title = _get_clean_title(data.get("filename", ""), data.get("full_text", ""))
        full_text = data.get("full_text", "")
        
        video_content = VideoContent(
            id=video_id,
            title=title,
            title_hi=title,
            description=f"Spiritual discourse. Duration: {int(data.get('duration', 0) / 60)} minutes.",
            description_hi="महाराज जी का आध्यात्मिक प्रवचन",
            thumbnail=f"/api/thumbnail/{video_id}",
            duration=data.get("duration", 0),
            transcript=full_text,
            transcript_chunks=data.get("chunks", []),
            summary_hi="",
            summary_en="",
            explanation_hi="",
            explanation_en="",
            created_at=data.get("created_at", datetime.now().isoformat()),
            category="pravachan",
            speaker="Maharaj Ji",
            tags="प्रवचन आध्यात्मिक spiritual"
        )
        
        videos[video_id] = video_content
        migrated += 1
        logger.info(f"Migrated: {video_id} - {title[:60]}")
    
    _save_videos_content(videos)
    logger.info(f"✅ Migration complete. Migrated {migrated} transcripts. Total: {len(videos)}")


def _get_clean_title(filename: str, full_text: str) -> str:
    """Extract a clean title from the filename or transcript text."""
    import re
    
    name = Path(filename).stem
    
    # If filename is UUID-like, use transcript text
    if re.match(r'^[a-f0-9]{8}-[a-f0-9]{3}$', name):
        first_line = full_text.strip().split('\n')[0][:100] if full_text else "Spiritual Discourse"
        first_line = re.sub(r'\s+', ' ', first_line).strip()
        if len(first_line) > 60:
            cut = first_line[:60].rfind(' ')
            if cut > 30:
                first_line = first_line[:cut]
        return first_line + "..." if len(full_text.strip()) > 60 else first_line
    
    # Clean YouTube-style filenames
    name = re.sub(r'\s*-\s*(?:Bhajan Marg|Sadhan Path|PremanandVicharOfficial|Shri Hit Premanand).*$', '', name, flags=re.IGNORECASE)
    name = name.replace('_', ' ').strip()
    name = re.sub(r'\s*MOTIVATIONAL\s+VIDEO\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    
    if not name or name.lower() in ('test', 'maharaj-voice', 'maharaj_voice'):
        # Fallback to transcript text
        first_line = full_text.strip()[:80] if full_text else "Spiritual Discourse"
        first_line = re.sub(r'\s+', ' ', first_line).strip()
        if len(first_line) > 60:
            cut = first_line[:60].rfind(' ')
            if cut > 30:
                first_line = first_line[:cut]
        return first_line + "..."
    
    return name


# Initialize - migrate existing transcripts on first load
def init_videos_content():
    """Initialize video content system and migrate existing data."""
    # Always run migration to pick up new transcripts and fix broken titles
    migrate_from_transcripts()

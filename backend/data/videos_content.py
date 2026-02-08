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
    
    # Themes and topics (auto-generated)
    main_topic: str = ""  # Primary topic in Hindi
    main_topic_en: str = ""  # Primary topic in English
    themes: List[str] = []  # Key themes in Hindi
    themes_en: List[str] = []  # Key themes in English
    key_teachings: List[str] = []  # Practical teachings
    
    # Audio URLs for pre-generated TTS
    summary_audio_hi: Optional[str] = None
    summary_audio_en: Optional[str] = None
    explanation_audio_hi: Optional[str] = None
    explanation_audio_en: Optional[str] = None
    
    # Metadata
    created_at: str
    category: str = "pravachan"  # pravachan, bhajan, discourse, etc.
    speaker: str = "Maharaj Ji"
    tags: List[str] = []


# Video content storage path
VIDEOS_CONTENT_FILE = settings.DATA_DIR / "videos_content.json"

# In-memory cache
_videos_cache: Optional[Dict[str, VideoContent]] = None


def _load_videos_content() -> Dict[str, VideoContent]:
    """Load all pre-processed video content (with in-memory caching)."""
    global _videos_cache
    
    if _videos_cache is not None:
        return _videos_cache
    
    if not VIDEOS_CONTENT_FILE.exists():
        _videos_cache = {}
        return _videos_cache
    
    try:
        with open(VIDEOS_CONTENT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        _videos_cache = {vid_id: VideoContent(**content) for vid_id, content in data.items()}
        return _videos_cache
    except Exception as e:
        logger.error(f"Failed to load videos content: {e}")
        return {}


def _save_videos_content(videos: Dict[str, VideoContent]):
    """Save all video content and update cache."""
    global _videos_cache
    try:
        data = {vid_id: content.model_dump() for vid_id, content in videos.items()}
        with open(VIDEOS_CONTENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _videos_cache = videos  # Update cache after successful save
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
            "duration": vid.duration,
            "category": vid.category,
            "speaker": vid.speaker,
            "tags": vid.tags,
            "created_at": vid.created_at
        }
        for vid in videos.values()
    ]


def get_video_detail(video_id: str, language: str = "hi") -> Optional[Dict[str, Any]]:
    """Get full video content for detail view."""
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
        "thumbnail": vid.thumbnail,
        "video_url": vid.video_url,
        "duration": vid.duration,
        "category": vid.category,
        "speaker": vid.speaker,
        "tags": vid.tags,
        
        # Full content
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
        "status": "complete"  # Pre-processed content is always complete
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
    This is a one-time migration utility.
    """
    import os
    
    transcript_dir = settings.TRANSCRIPT_DIR
    if not transcript_dir.exists():
        logger.warning("No transcripts directory found")
        return
    
    videos = _load_videos_content()
    migrated = 0
    
    for transcript_file in transcript_dir.glob("*.json"):
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            video_id = data.get("id", transcript_file.stem)
            
            if video_id in videos:
                continue  # Already migrated
            
            # Create video content from transcript
            title = data.get("title", "Spiritual Discourse")
            full_text = data.get("full_text", "")
            
            # Use first 50 chars of title for both languages
            title_short = title[:100] + "..." if len(title) > 100 else title
            
            video_content = VideoContent(
                id=video_id,
                title=title_short,  # Will be in Hindi from transcription
                title_hi=title_short,
                description="Spiritual discourse by Maharaj Ji",
                description_hi="महाराज जी का आध्यात्मिक प्रवचन",
                thumbnail=f"/api/thumbnail/{video_id}",
                duration=data.get("duration", 0),
                transcript=full_text,
                transcript_chunks=data.get("chunks", []),
                summary_hi="",  # To be generated
                summary_en="",
                explanation_hi="",
                explanation_en="",
                created_at=data.get("created_at", datetime.now().isoformat()),
                category="pravachan",
                speaker="Maharaj Ji"
            )
            
            videos[video_id] = video_content
            migrated += 1
            logger.info(f"Migrated: {video_id}")
            
        except Exception as e:
            logger.error(f"Failed to migrate {transcript_file}: {e}")
    
    _save_videos_content(videos)
    logger.info(f"✅ Migration complete. Migrated {migrated} transcripts.")


# Initialize - migrate existing transcripts on first load
def init_videos_content():
    """Initialize video content system and migrate existing data."""
    if not VIDEOS_CONTENT_FILE.exists():
        logger.info("Initializing video content store...")
        migrate_from_transcripts()

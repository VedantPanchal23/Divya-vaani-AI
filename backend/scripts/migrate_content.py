"""
Migration Script: Convert existing transcripts to pre-processed video content.
Run this once to migrate your existing data.

Usage: python migrate_content.py
"""
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from data.videos_content import VideoContent, add_video_content, VIDEOS_CONTENT_FILE
from core import llm_engine, tts_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_transcript(transcript_data: dict) -> VideoContent:
    """Convert a transcript to VideoContent with generated summary and explanation."""
    
    video_id = transcript_data.get("id")
    title = transcript_data.get("title", "Spiritual Discourse")
    full_text = transcript_data.get("full_text", "")
    duration = transcript_data.get("duration", 0)
    chunks = transcript_data.get("chunks", [])
    created_at = transcript_data.get("created_at", datetime.now().isoformat())
    
    logger.info(f"Processing: {video_id} - {title[:50]}...")
    
    # Generate summaries
    logger.info("  Generating Hindi summary...")
    summary_hi = await llm_engine.generate_summary(full_text, "hi")
    
    logger.info("  Generating English summary...")
    summary_en = await llm_engine.generate_summary(full_text, "en")
    
    # Generate explanations
    logger.info("  Generating Hindi explanation...")
    explanation_hi = await llm_engine.generate_explanation(full_text, "hi")
    
    logger.info("  Generating English explanation...")
    explanation_en = await llm_engine.generate_explanation(full_text, "en")
    
    # Generate TTS audio (optional - can be slow)
    summary_audio_hi = ""
    summary_audio_en = ""
    explanation_audio_hi = ""
    explanation_audio_en = ""
    
    try:
        logger.info("  Generating audio files...")
        summary_audio_hi = await tts_engine.generate_speech_async(summary_hi, "hi", mode="clone")
        summary_audio_en = await tts_engine.generate_speech_async(summary_en, "en", mode="clone")
        explanation_audio_hi = await tts_engine.generate_speech_async(explanation_hi, "hi", mode="clone")
        explanation_audio_en = await tts_engine.generate_speech_async(explanation_en, "en", mode="clone")
    except Exception as e:
        logger.warning(f"  Audio generation failed: {e}")
    
    # Create VideoContent
    video_content = VideoContent(
        id=video_id,
        title=summary_en[:100] if summary_en else title[:100],  # Use English title
        title_hi=title[:100],  # Original Hindi title
        description=f"Spiritual discourse from Maharaj Ji's teachings. Duration: {int(duration/60)} minutes.",
        description_hi="महाराज जी के आध्यात्मिक प्रवचन",
        thumbnail=f"/api/thumbnail/{video_id}",
        duration=duration,
        transcript=full_text,
        transcript_chunks=chunks,
        summary_hi=summary_hi,
        summary_en=summary_en,
        explanation_hi=explanation_hi,
        explanation_en=explanation_en,
        summary_audio_hi=summary_audio_hi,
        summary_audio_en=summary_audio_en,
        explanation_audio_hi=explanation_audio_hi,
        explanation_audio_en=explanation_audio_en,
        created_at=created_at,
        category="pravachan",
        speaker="Maharaj Ji",
        tags=["spiritual", "pravachan", "hindi"]
    )
    
    return video_content


async def migrate_all():
    """Migrate all existing transcripts to video content."""
    
    transcript_dir = settings.TRANSCRIPT_DIR
    if not transcript_dir.exists():
        logger.error("No transcripts directory found")
        return
    
    transcript_files = list(transcript_dir.glob("*.json"))
    logger.info(f"Found {len(transcript_files)} transcripts to migrate")
    
    # Load existing videos to skip already migrated
    existing_videos = set()
    if VIDEOS_CONTENT_FILE.exists():
        with open(VIDEOS_CONTENT_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
            existing_videos = set(existing.keys())
    
    migrated = 0
    for transcript_file in transcript_files:
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            video_id = data.get("id", transcript_file.stem)
            
            if video_id in existing_videos:
                logger.info(f"Skipping already migrated: {video_id}")
                continue
            
            video_content = await migrate_transcript(data)
            add_video_content(video_content)
            migrated += 1
            
            logger.info(f"✅ Migrated: {video_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to migrate {transcript_file}: {e}")
    
    logger.info(f"\n✅ Migration complete. Migrated {migrated} transcripts.")


async def create_quick_migration():
    """Quick migration without generating summaries (uses empty placeholders)."""
    
    transcript_dir = settings.TRANSCRIPT_DIR
    if not transcript_dir.exists():
        logger.error("No transcripts directory found")
        return
    
    transcript_files = list(transcript_dir.glob("*.json"))
    logger.info(f"Found {len(transcript_files)} transcripts for quick migration")
    
    videos = {}
    
    for transcript_file in transcript_files:
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            video_id = data.get("id", transcript_file.stem)
            title = data.get("title", "Spiritual Discourse")
            full_text = data.get("full_text", "")
            duration = data.get("duration", 0)
            chunks = data.get("chunks", [])
            created_at = data.get("created_at", datetime.now().isoformat())
            
            # Create short title from full text
            title_short = title[:100] + "..." if len(title) > 100 else title
            
            video_content = VideoContent(
                id=video_id,
                title=title_short,
                title_hi=title_short,
                description="Spiritual discourse from Maharaj Ji's teachings",
                description_hi="महाराज जी के आध्यात्मिक प्रवचन",
                thumbnail=f"/api/thumbnail/{video_id}",
                duration=duration,
                transcript=full_text,
                transcript_chunks=chunks,
                summary_hi="",  # To be generated on first view
                summary_en="",
                explanation_hi="",
                explanation_en="",
                created_at=created_at,
                category="pravachan",
                speaker="Maharaj Ji",
                tags=["spiritual", "pravachan", "hindi"]
            )
            
            videos[video_id] = video_content.model_dump()
            logger.info(f"✅ Added: {video_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed: {transcript_file}: {e}")
    
    # Save all at once
    with open(VIDEOS_CONTENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n✅ Quick migration complete. Added {len(videos)} videos.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate transcripts to video content")
    parser.add_argument("--quick", action="store_true", help="Quick migration without AI generation")
    parser.add_argument("--full", action="store_true", help="Full migration with AI-generated summaries")
    
    args = parser.parse_args()
    
    if args.full:
        asyncio.run(migrate_all())
    else:
        # Default to quick migration
        asyncio.run(create_quick_migration())

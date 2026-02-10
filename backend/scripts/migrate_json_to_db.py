"""
Migrate videos_content.json → database.
Run once after setting up the database to import existing video data.

Usage:
    python -m scripts.migrate_json_to_db
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR
from db.database import init_db, close_db, _get_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


async def migrate():
    json_path = DATA_DIR / "videos_content.json"
    if not json_path.exists():
        logger.warning(f"No videos_content.json found at {json_path} — nothing to migrate.")
        return

    # Initialize DB
    await init_db()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # videos_content.json is a dict keyed by video ID
    if isinstance(data, dict):
        videos = list(data.values())
    elif isinstance(data, list):
        videos = data
    else:
        logger.error("Unexpected JSON format in videos_content.json")
        return

    logger.info(f"Found {len(videos)} videos to migrate")

    from db import crud

    factory = _get_session_factory()
    async with factory() as db:
        migrated = 0
        skipped = 0
        for v in videos:
            video_id = v.get("id")
            if not video_id:
                logger.warning(f"Skipping video without ID: {v.get('title', '?')}")
                skipped += 1
                continue

            # Map JSON fields to DB model fields
            video_data = {
                "id": video_id,
                "title": v.get("title", ""),
                "title_hi": v.get("title_hi", ""),
                "description": v.get("description", ""),
                "description_hi": v.get("description_hi", ""),
                "thumbnail": v.get("thumbnail", ""),
                "video_url": v.get("video_url", ""),
                "duration": v.get("duration", 0.0),
                "category": v.get("category", "pravachan"),
                "speaker": v.get("speaker", "Maharaj Ji"),
                "tags": v.get("tags", []),
                "transcript": v.get("transcript", ""),
                "transcript_chunks": v.get("transcript_chunks", []),
                "summary_hi": v.get("summary_hi", ""),
                "summary_en": v.get("summary_en", ""),
                "explanation_hi": v.get("explanation_hi", ""),
                "explanation_en": v.get("explanation_en", ""),
                "main_topic": v.get("main_topic", ""),
                "main_topic_en": v.get("main_topic_en", ""),
                "themes": v.get("themes", []),
                "themes_en": v.get("themes_en", []),
                "key_teachings": v.get("key_teachings", []),
                "summary_audio_hi": v.get("summary_audio_hi"),
                "summary_audio_en": v.get("summary_audio_en"),
                "explanation_audio_hi": v.get("explanation_audio_hi"),
                "explanation_audio_en": v.get("explanation_audio_en"),
            }

            try:
                await crud.upsert_video(db, video_data)
                migrated += 1
                logger.info(f"  ✅ Migrated: {video_id} — {v.get('title', '')[:50]}")
            except Exception as e:
                logger.error(f"  ❌ Failed to migrate {video_id}: {e}")
                skipped += 1

    logger.info(f"\nMigration complete: {migrated} migrated, {skipped} skipped")
    await close_db()


if __name__ == "__main__":
    asyncio.run(migrate())

"""Video content routes — list, detail, summary, delete, media serving."""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from db import crud
from core import llm_engine
from ._helpers import _safe_path, _verify_admin_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Re-use upload status store so delete can clean it up
from .upload_routes import _status


@router.get("/videos")
async def list_videos(db: AsyncSession = Depends(get_db)):
    """Get all pre-loaded videos with basic info for cards."""
    try:
        videos = await crud.get_all_videos_db(db)
        return {"videos": [crud.video_to_card(v) for v in videos], "total": len(videos)}
    except Exception as e:
        logger.error(f"Failed to get videos: {e}")
        raise HTTPException(500, f"Failed to get videos: {e}")


@router.get("/videos/{video_id}")
async def get_video(video_id: str, language: str = "hi", db: AsyncSession = Depends(get_db)):
    """Get full video content including transcript, summary, and explanation."""
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    return crud.video_to_detail(video, language)


@router.get("/videos/{video_id}/summary")
async def get_video_summary(video_id: str, language: str = "hi", db: AsyncSession = Depends(get_db)):
    """Get video summary and explanation."""
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    detail = crud.video_to_detail(video, language)
    return {
        "id": video_id,
        "summary": detail.get("summary", ""),
        "summary_hi": detail.get("summary_hi", ""),
        "summary_en": detail.get("summary_en", ""),
        "explanation": detail.get("explanation", ""),
        "explanation_hi": detail.get("explanation_hi", ""),
        "explanation_en": detail.get("explanation_en", ""),
        "summary_audio": detail.get("summary_audio", ""),
        "explanation_audio": detail.get("explanation_audio", "")
    }


@router.post("/videos/{video_id}/generate-summary", dependencies=[Depends(_verify_admin_key)])
async def generate_video_summary(video_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Generate summary and explanation for a video on demand. Requires admin key."""
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    if video.summary_hi and video.summary_en:
        return {"status": "exists", "message": "Summary already exists"}

    async def generate_task():
        try:
            transcript = video.transcript or ""
            if not transcript:
                return
            summary_hi = await llm_engine.generate_summary(transcript, "hi")
            summary_en = await llm_engine.generate_summary(transcript, "en")
            explanation_hi = await llm_engine.generate_explanation(transcript, "hi")
            explanation_en = await llm_engine.generate_explanation(transcript, "en")

            # Update in DB
            from db.database import _get_session_factory
            factory = _get_session_factory()
            async with factory() as session:
                await crud.update_video_fields(session, video_id, {
                    "summary_hi": summary_hi,
                    "summary_en": summary_en,
                    "explanation_hi": explanation_hi,
                    "explanation_en": explanation_en,
                })
            logger.info(f"✅ Generated summary for video: {video_id}")
        except Exception as e:
            logger.error(f"Failed to generate summary for {video_id}: {e}")

    background_tasks.add_task(generate_task)
    return {"status": "generating", "message": "Summary generation started"}


@router.delete("/videos/{video_id}", dependencies=[Depends(_verify_admin_key)])
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a video and all its associated data. Requires admin key."""
    video = await crud.get_video_by_id(db, video_id)
    if not video:
        raise HTTPException(404, "Video not found")

    await crud.delete_video_db(db, video_id)

    # Delete uploaded media in all formats
    for ext in [".mp4", ".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac"]:
        path = settings.UPLOAD_DIR / f"{video_id}{ext}"
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    # Delete transcript
    for path in [settings.TRANSCRIPT_DIR / f"{video_id}.json"]:
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    # Delete thumbnails
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        thumb = settings.DATA_DIR / "thumbnails" / f"{video_id}{ext}"
        if thumb.exists():
            try:
                thumb.unlink()
            except Exception:
                pass

    _status.pop(video_id, None)
    logger.info(f"✅ Deleted video: {video_id}")
    return {"status": "deleted", "id": video_id}


@router.get("/thumbnail/{video_id}")
async def get_thumbnail(video_id: str):
    """Serve video thumbnail image."""
    if not video_id.replace('-', '').replace('_', '').isalnum():
        raise HTTPException(400, "Invalid video ID")
    thumbnail_dir = settings.DATA_DIR / "thumbnails"
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        path = _safe_path(thumbnail_dir, f"{video_id}{ext}")
        if path.exists():
            return FileResponse(path)
    default_thumb = thumbnail_dir / "default.jpg"
    if default_thumb.exists():
        return FileResponse(default_thumb)
    raise HTTPException(404, "Thumbnail not found")


@router.get("/video/{video_id}")
async def get_video_file(video_id: str):
    """Serve uploaded video file."""
    if not video_id.replace('-', '').replace('_', '').isalnum():
        raise HTTPException(400, "Invalid video ID")
    upload_dir = settings.DATA_DIR / "uploads"
    for ext in [".webm", ".mp4", ".mkv", ".avi", ".mov", ".m4v"]:
        path = _safe_path(upload_dir, f"{video_id}{ext}")
        if path.exists():
            media_types = {
                ".webm": "video/webm", ".mp4": "video/mp4",
                ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
                ".mov": "video/quicktime", ".m4v": "video/x-m4v"
            }
            return FileResponse(path, media_type=media_types.get(ext, "video/mp4"), filename=f"{video_id}{ext}")
    raise HTTPException(404, "Video file not found")

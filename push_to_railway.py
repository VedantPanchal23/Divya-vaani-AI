"""
Push local video data from SQLite to Railway (PostgreSQL) via the /api/videos/import endpoint.
Also uploads thumbnail and video media files.
Usage: python push_to_railway.py
"""
import sqlite3
import json
import requests
from pathlib import Path

# ── Config ──
LOCAL_DB = "backend/data/divyavaani.db"
UPLOADS_DIR = Path("backend/data/uploads")
THUMBNAILS_DIR = Path("backend/data/thumbnails")
RAILWAY_URL = "https://divya-vaani-ai-production-6a46.up.railway.app"
ADMIN_KEY = "FT7UOKrP9LxeL2WBGNZ_o7NNOELsRyKB6P7sEGBopKY"

def get_local_videos():
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM videos")
    rows = cur.fetchall()
    conn.close()

    videos = []
    for row in rows:
        video = dict(row)
        # Parse JSON fields
        for field in ("tags", "transcript_chunks", "themes", "themes_en", "key_teachings"):
            val = video.get(field)
            if isinstance(val, str):
                try:
                    video[field] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
        # Convert datetime fields to strings
        for field in ("created_at", "updated_at"):
            val = video.get(field)
            if val and not isinstance(val, str):
                video[field] = str(val)
        videos.append(video)
    return videos


def push_video(video_data):
    resp = requests.post(
        f"{RAILWAY_URL}/api/videos/import",
        json=video_data,
        headers={"X-Admin-Key": ADMIN_KEY},
        timeout=30,
    )
    return resp.status_code, resp.json()


def upload_media(video_id, file_path):
    """Upload a media file (thumbnail or video) to Railway."""
    with open(file_path, "rb") as f:
        resp = requests.post(
            f"{RAILWAY_URL}/api/videos/{video_id}/upload-media",
            headers={"X-Admin-Key": ADMIN_KEY},
            files={"file": (file_path.name, f)},
            timeout=300,
        )
    return resp.status_code, resp.json()


def find_media(video_id):
    """Find local thumbnail and video files for a given video ID."""
    files = {}
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        p = THUMBNAILS_DIR / f"{video_id}{ext}"
        if p.exists():
            files["thumbnail"] = p
            break
    for ext in [".mp4", ".webm", ".mkv", ".avi", ".mov"]:
        p = UPLOADS_DIR / f"{video_id}{ext}"
        if p.exists():
            files["video"] = p
            break
    return files


def main():
    videos = get_local_videos()
    print(f"Found {len(videos)} videos in local SQLite")

    for v in videos:
        title = v.get("title", "?")[:60]
        print(f"\n→ Pushing: {v['id']} | {title}")
        status, result = push_video(v)
        if status == 200:
            print(f"  ✅ Data imported: {result}")
        else:
            print(f"  ❌ Data failed ({status}): {result}")
            continue

        # Upload media files
        media = find_media(v["id"])
        for media_type, file_path in media.items():
            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"  📤 Uploading {media_type}: {file_path.name} ({size_mb:.1f} MB)...")
            ms, mr = upload_media(v["id"], file_path)
            if ms == 200:
                print(f"  ✅ {media_type} uploaded: {mr}")
            else:
                print(f"  ❌ {media_type} failed ({ms}): {mr}")

    # Verify
    resp = requests.get(f"{RAILWAY_URL}/api/videos", timeout=15)
    data = resp.json()
    print(f"\n{'='*50}")
    print(f"Railway now has {data.get('total', 0)} videos")


if __name__ == "__main__":
    main()

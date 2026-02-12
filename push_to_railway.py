"""
Push local video data from SQLite to Railway (PostgreSQL) via the /api/videos/import endpoint.
Also uploads thumbnail and video media files.
Skips already-uploaded items. Retries large uploads on timeout.
Usage: python push_to_railway.py
"""
import sqlite3
import json
import time
import requests
from pathlib import Path

# ── Config ──
LOCAL_DB = "backend/data/divyavaani.db"
UPLOADS_DIR = Path("backend/data/uploads")
THUMBNAILS_DIR = Path("backend/data/thumbnails")
RAILWAY_URL = "https://divya-vaani-ai-production-6a46.up.railway.app"
ADMIN_KEY = "FT7UOKrP9LxeL2WBGNZ_o7NNOELsRyKB6P7sEGBopKY"
MAX_RETRIES = 3

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


def check_remote_exists(endpoint):
    """Check if a resource exists on Railway (HEAD/GET check)."""
    try:
        resp = requests.head(f"{RAILWAY_URL}{endpoint}", timeout=10, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        try:
            resp = requests.get(f"{RAILWAY_URL}{endpoint}", timeout=10, stream=True)
            resp.close()
            return resp.status_code == 200
        except Exception:
            return False


def upload_media(video_id, file_path, retries=MAX_RETRIES):
    """Upload a media file (thumbnail or video) to Railway with retry logic."""
    file_size = file_path.stat().st_size
    # Scale timeout: 60s base + 10s per MB
    timeout = max(120, 60 + int(file_size / (1024 * 1024)) * 10)

    for attempt in range(1, retries + 1):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{RAILWAY_URL}/api/videos/{video_id}/upload-media",
                    headers={"X-Admin-Key": ADMIN_KEY},
                    files={"file": (file_path.name, f)},
                    timeout=timeout,
                )
            return resp.status_code, resp.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < retries:
                wait = 10 * attempt
                print(f"    ⚠️  Attempt {attempt}/{retries} failed (timeout). Retrying in {wait}s...")
                time.sleep(wait)
            else:
                return 0, {"error": f"Upload failed after {retries} attempts: {e}"}


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
    # Get existing videos on Railway to skip re-uploads
    try:
        resp = requests.get(f"{RAILWAY_URL}/api/videos", timeout=15)
        remote_ids = {v["id"] for v in resp.json().get("videos", [])}
    except Exception:
        remote_ids = set()

    videos = get_local_videos()
    print(f"Found {len(videos)} local videos, {len(remote_ids)} already on Railway")

    for v in videos:
        vid = v["id"]
        title = v.get("title", "?")[:60]
        print(f"\n→ {vid} | {title}")

        # Import video data (upsert — safe to re-run)
        status, result = push_video(v)
        if status == 200:
            print(f"  ✅ Data imported")
        else:
            print(f"  ❌ Data failed ({status}): {result}")
            continue

        # Upload media files, skip if already exists
        media = find_media(vid)
        for media_type, file_path in media.items():
            check_url = f"/api/{'thumbnail' if media_type == 'thumbnail' else 'video'}/{vid}"
            if check_remote_exists(check_url):
                print(f"  ⏭️  {media_type} already exists, skipping")
                continue

            size_mb = file_path.stat().st_size / (1024 * 1024)
            print(f"  📤 Uploading {media_type}: {file_path.name} ({size_mb:.1f} MB)...")
            ms, mr = upload_media(vid, file_path)
            if ms == 200:
                print(f"  ✅ {media_type} uploaded ({mr.get('size_mb', '?')} MB)")
            else:
                print(f"  ❌ {media_type} failed ({ms}): {mr}")

    # Verify
    resp = requests.get(f"{RAILWAY_URL}/api/videos", timeout=15)
    data = resp.json()
    print(f"\n{'='*50}")
    print(f"Railway now has {data.get('total', 0)} videos")


if __name__ == "__main__":
    main()

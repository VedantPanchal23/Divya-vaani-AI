"""
Push local video data from SQLite to Railway (PostgreSQL) via the /api/videos/import endpoint.
Usage: python push_to_railway.py
"""
import sqlite3
import json
import requests

# ── Config ──
LOCAL_DB = "backend/data/divyavaani.db"
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


def main():
    videos = get_local_videos()
    print(f"Found {len(videos)} videos in local SQLite")

    for v in videos:
        title = v.get("title", "?")[:60]
        print(f"\n→ Pushing: {v['id']} | {title}")
        status, result = push_video(v)
        if status == 200:
            print(f"  ✅ Imported: {result}")
        else:
            print(f"  ❌ Failed ({status}): {result}")

    # Verify
    resp = requests.get(f"{RAILWAY_URL}/api/videos", timeout=15)
    data = resp.json()
    print(f"\n{'='*50}")
    print(f"Railway now has {data.get('total', 0)} videos")


if __name__ == "__main__":
    main()

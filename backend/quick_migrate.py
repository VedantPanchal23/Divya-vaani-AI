"""
Quick migration: Run this to migrate existing transcripts to video content.
No AI generation - just structure migration.
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Get paths
BACKEND_DIR = Path(__file__).parent.absolute()
DATA_DIR = BACKEND_DIR / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
VIDEOS_CONTENT_FILE = DATA_DIR / "videos_content.json"

def migrate():
    """Quick migration without AI processing."""
    
    if not TRANSCRIPT_DIR.exists():
        print("❌ No transcripts directory found")
        return
    
    transcript_files = list(TRANSCRIPT_DIR.glob("*.json"))
    print(f"Found {len(transcript_files)} transcripts")
    
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
            
            # Create short title
            title_short = title[:100] + "..." if len(title) > 100 else title
            
            video = {
                "id": video_id,
                "title": title_short,
                "title_hi": title_short,
                "description": "Spiritual discourse from Maharaj Ji's teachings",
                "description_hi": "महाराज जी के आध्यात्मिक प्रवचन",
                "thumbnail": f"/api/thumbnail/{video_id}",
                "video_url": None,
                "duration": duration,
                "transcript": full_text,
                "transcript_chunks": chunks,
                "summary_hi": "",
                "summary_en": "",
                "explanation_hi": "",
                "explanation_en": "",
                "summary_audio_hi": None,
                "summary_audio_en": None,
                "explanation_audio_hi": None,
                "explanation_audio_en": None,
                "created_at": created_at,
                "category": "pravachan",
                "speaker": "Maharaj Ji",
                "tags": ["spiritual", "pravachan", "hindi"]
            }
            
            videos[video_id] = video
            print(f"✅ {video_id}: {title_short[:40]}...")
            
        except Exception as e:
            print(f"❌ {transcript_file}: {e}")
    
    # Save
    with open(VIDEOS_CONTENT_FILE, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Migration complete! Created {len(videos)} video entries.")
    print(f"   Saved to: {VIDEOS_CONTENT_FILE}")

if __name__ == "__main__":
    migrate()

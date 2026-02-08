"""
Clean up videos_content.json - remove videos without proper summaries
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
VIDEOS_FILE = DATA_DIR / "videos_content.json"

def cleanup_videos():
    if not VIDEOS_FILE.exists():
        print("No videos_content.json found")
        return
    
    with open(VIDEOS_FILE, 'r', encoding='utf-8') as f:
        videos = json.load(f)
    
    print(f"Total videos before cleanup: {len(videos)}")
    
    # Keep only videos with proper summaries
    cleaned = {}
    removed = []
    
    for vid_id, video in videos.items():
        summary_hi = video.get('summary_hi', '')
        summary_en = video.get('summary_en', '')
        
        # Keep if has proper summary (not empty)
        if summary_hi and len(summary_hi) > 50:
            cleaned[vid_id] = video
        else:
            removed.append(f"{vid_id[:12]} - {video.get('title_hi', video.get('title', 'N/A'))[:40]}")
    
    print(f"\nVideos with proper summaries: {len(cleaned)}")
    print(f"Videos removed (no summary): {len(removed)}")
    
    if removed:
        print("\nRemoved videos:")
        for r in removed:
            print(f"  - {r}")
    
    # Save cleaned data
    with open(VIDEOS_FILE, 'w', encoding='utf-8') as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Cleanup complete! {len(cleaned)} videos remaining.")


if __name__ == "__main__":
    cleanup_videos()

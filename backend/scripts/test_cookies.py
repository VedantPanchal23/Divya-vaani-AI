"""Quick test: verify cookies.txt works with yt-dlp for YouTube authentication."""
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp not installed")
    sys.exit(1)

cookies_path = Path(__file__).parent.parent / "cookies.txt"
if not cookies_path.exists():
    print(f"ERROR: cookies.txt not found at {cookies_path}")
    sys.exit(1)

# Use the same video ID from the error screenshot
test_url = "https://www.youtube.com/watch?v=vI2NIp-JQMI"

print(f"Testing YouTube access with cookies: {cookies_path}")
print(f"Test URL: {test_url}")
print()

ydl_opts = {
    "cookiefile": str(cookies_path),
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "format": "bestaudio/best",
    "extractor_args": {
        "youtube": {
            "player_client": ["mweb", "android"],
        }
    },
}

try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(test_url, download=False)
    title = info.get("title", "Unknown")
    duration = info.get("duration", 0)
    video_id = info.get("id", "?")
    print(f"SUCCESS! YouTube authentication works.")
    print(f"  Title: {title}")
    print(f"  ID: {video_id}")
    print(f"  Duration: {duration}s")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

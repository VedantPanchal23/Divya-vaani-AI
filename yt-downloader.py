#!/usr/bin/env python3
"""
YouTube / audio downloader utility for Divya Vaani AI.
Downloads videos or extracts audio for transcription.
"""
import argparse
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("Error: yt-dlp is not installed. Run: pip install yt-dlp")
    sys.exit(1)


def download(url: str, output_dir: str = ".", audio_only: bool = False) -> None:
    """Download a video or extract audio from a URL."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out / "%(title)s.%(ext)s"),
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "http_chunk_size": 1048576,  # 1 MB chunks
    }

    if audio_only:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts["format"] = (
            "bestvideo[ext=mp4][filesize<100M]+bestaudio[ext=m4a]/"
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<100M]/"
            "best[height<=720][ext=mp4]/best"
        )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        print(f"\n✅ Download complete → {output_dir}")
    except yt_dlp.utils.DownloadError as e:
        print(f"\n❌ Download failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube videos or audio for Divya Vaani AI"
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "-o", "--output",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "-a", "--audio-only",
        action="store_true",
        help="Extract audio only (MP3)",
    )
    args = parser.parse_args()
    download(args.url, args.output, args.audio_only)


if __name__ == "__main__":
    main()

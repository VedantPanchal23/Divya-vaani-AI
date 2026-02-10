"""
Admin Tool: Upload and Process Videos
Processes videos and stores transcriptions, summaries, and explanations.

Usage:
    python admin_upload.py <video_file_path>
    python admin_upload.py --folder <folder_path>
    python admin_upload.py --list
    python admin_upload.py --delete <video_id>
    python admin_upload.py --regenerate <video_id>
"""
import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from db.database import init_db, _get_session_factory
from db import crud
from core import transcriber, llm_engine, rag_engine, tts_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


async def process_video(file_path: Path, generate_audio: bool = False) -> VideoContent:
    """
    Process a single video file:
    1. Transcribe audio
    2. Generate summary (Hindi + English)
    3. Generate explanation (Hindi + English)
    4. Optionally generate TTS audio
    5. Index for RAG search
    """
    
    print(f"\n{'='*60}")
    print(f"📹 Processing: {file_path.name}")
    print(f"{'='*60}\n")
    
    # Step 1: Transcribe
    print("📝 Step 1/4: Transcribing audio...")
    
    def progress_callback(current, total, msg):
        print(f"   [{current}/{total}] {msg}")
    
    transcript = await transcriber.transcribe_audio(
        file_id=file_path.stem[:12],
        file_path=file_path,
        filename=file_path.name,
        progress_callback=progress_callback
    )
    
    print(f"   ✅ Transcribed: {len(transcript.full_text)} chars, {len(transcript.chunks)} chunks")
    
    # Step 2: Generate Summary
    print("\n📋 Step 2/4: Generating summaries...")
    
    print("   Generating Hindi summary...")
    summary_hi = await llm_engine.generate_summary(transcript.full_text, "hi")
    print(f"   ✅ Hindi summary: {len(summary_hi)} chars")
    
    print("   Generating English summary...")
    summary_en = await llm_engine.generate_summary(transcript.full_text, "en")
    print(f"   ✅ English summary: {len(summary_en)} chars")
    
    # Step 3: Generate Explanation
    print("\n💡 Step 3/4: Generating explanations...")
    
    print("   Generating Hindi explanation...")
    explanation_hi = await llm_engine.generate_explanation(transcript.full_text, "hi")
    print(f"   ✅ Hindi explanation: {len(explanation_hi)} chars")
    
    print("   Generating English explanation...")
    explanation_en = await llm_engine.generate_explanation(transcript.full_text, "en")
    print(f"   ✅ English explanation: {len(explanation_en)} chars")
    
    # Step 4: Generate TTS Audio (optional)
    summary_audio_hi = ""
    summary_audio_en = ""
    explanation_audio_hi = ""
    explanation_audio_en = ""
    
    if generate_audio:
        print("\n🔊 Step 4/4: Generating audio...")
        try:
            print("   Generating Hindi summary audio...")
            summary_audio_hi = await tts_engine.generate_speech_async(summary_hi, "hi", mode="clone")
            
            print("   Generating English summary audio...")
            summary_audio_en = await tts_engine.generate_speech_async(summary_en, "en", mode="clone")
            
            print("   Generating Hindi explanation audio...")
            explanation_audio_hi = await tts_engine.generate_speech_async(explanation_hi, "hi", mode="clone")
            
            print("   Generating English explanation audio...")
            explanation_audio_en = await tts_engine.generate_speech_async(explanation_en, "en", mode="clone")
            
            print("   ✅ Audio files generated")
        except Exception as e:
            print(f"   ⚠️ Audio generation failed: {e}")
    else:
        print("\n⏭️  Step 4/4: Skipping audio generation (use --audio to enable)")
    
    # Create short title from summary or transcript
    title_hi = transcript.title[:100] if transcript.title else transcript.full_text[:100]
    title_en = summary_en.split('.')[0][:100] if summary_en else "Spiritual Discourse"
    
    # Build video data dict
    video_data = {
        "id": transcript.id,
        "title": title_en,
        "title_hi": title_hi,
        "description": f"Spiritual discourse. Duration: {int(transcript.duration/60)} minutes.",
        "description_hi": "महाराज जी का आध्यात्मिक प्रवचन",
        "thumbnail": f"/api/thumbnail/{transcript.id}",
        "video_url": None,
        "duration": transcript.duration,
        "transcript": transcript.full_text,
        "transcript_chunks": [{
            "id": c.id,
            "text": c.text,
            "start_time": c.start_time,
            "end_time": c.end_time
        } for c in transcript.chunks],
        "summary_hi": summary_hi,
        "summary_en": summary_en,
        "explanation_hi": explanation_hi,
        "explanation_en": explanation_en,
        "summary_audio_hi": summary_audio_hi,
        "summary_audio_en": summary_audio_en,
        "explanation_audio_hi": explanation_audio_hi,
        "explanation_audio_en": explanation_audio_en,
        "created_at": datetime.now(timezone.utc),
        "category": "pravachan",
        "speaker": "Maharaj Ji",
        "tags": ["spiritual", "pravachan", "hindi"],
    }
    
    # Index for RAG search
    print("\n📚 Indexing for search...")
    try:
        rag_engine.index_transcript(transcript)
        print("   ✅ Indexed for RAG search")
    except Exception as e:
        print(f"   ⚠️ Indexing failed: {e}")
    
    # Save to DB
    factory = _get_session_factory()
    async with factory() as db:
        video = await crud.upsert_video(db, video_data)
    
    print(f"\n{'='*60}")
    print(f"✅ SUCCESS: {transcript.id}")
    print(f"   Title: {title_hi[:50]}...")
    print(f"   Duration: {int(transcript.duration/60)}m {int(transcript.duration%60)}s")
    print(f"{'='*60}\n")
    
    return video


async def regenerate_content(video_id: str, generate_audio: bool = False):
    """Regenerate summary and explanation for an existing video."""
    
    factory = _get_session_factory()
    async with factory() as db:
        video = await crud.get_video_by_id(db, video_id)
    
    if not video:
        print(f"❌ Video not found: {video_id}")
        return
    
    transcript = video.transcript or ""
    if not transcript:
        print(f"❌ No transcript found for: {video_id}")
        return
    
    print(f"\n{'='*60}")
    print(f"🔄 Regenerating: {video_id}")
    print(f"{'='*60}\n")
    
    # Generate summaries
    print("📋 Generating summaries...")
    summary_hi = await llm_engine.generate_summary(transcript, "hi")
    summary_en = await llm_engine.generate_summary(transcript, "en")
    print(f"   ✅ Summaries generated")
    
    # Generate explanations
    print("💡 Generating explanations...")
    explanation_hi = await llm_engine.generate_explanation(transcript, "hi")
    explanation_en = await llm_engine.generate_explanation(transcript, "en")
    print(f"   ✅ Explanations generated")
    
    # Audio (optional)
    updates = {
        "summary_hi": summary_hi,
        "summary_en": summary_en,
        "explanation_hi": explanation_hi,
        "explanation_en": explanation_en,
    }
    
    if generate_audio:
        print("🔊 Generating audio...")
        try:
            updates["summary_audio_hi"] = await tts_engine.generate_speech_async(summary_hi, "hi", mode="clone")
            updates["summary_audio_en"] = await tts_engine.generate_speech_async(summary_en, "en", mode="clone")
            updates["explanation_audio_hi"] = await tts_engine.generate_speech_async(explanation_hi, "hi", mode="clone")
            updates["explanation_audio_en"] = await tts_engine.generate_speech_async(explanation_en, "en", mode="clone")
            print("   ✅ Audio generated")
        except Exception as e:
            print(f"   ⚠️ Audio failed: {e}")
    
    # Update in DB
    factory = _get_session_factory()
    async with factory() as db:
        await crud.update_video_fields(db, video_id, updates)
    print(f"\n✅ Regenerated: {video_id}")


async def process_folder(folder_path: Path, generate_audio: bool = False):
    """Process all video/audio files in a folder."""
    
    valid_extensions = {'.mp3', '.mp4', '.wav', '.m4a', '.webm', '.ogg', '.flac'}
    files = [f for f in folder_path.iterdir() if f.suffix.lower() in valid_extensions]
    
    if not files:
        print(f"❌ No valid media files found in {folder_path}")
        return
    
    print(f"\n📂 Found {len(files)} files to process\n")
    
    for i, file_path in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Processing {file_path.name}...")
        try:
            await process_video(file_path, generate_audio)
        except Exception as e:
            print(f"❌ Failed to process {file_path.name}: {e}")
            logger.exception(e)
    
    print(f"\n✅ Processed {len(files)} files")


async def list_videos():
    """List all videos in the DB."""
    factory = _get_session_factory()
    async with factory() as db:
        db_videos = await crud.get_all_videos_db(db)
    
    if not db_videos:
        print("📭 No videos in database")
        return
    
    print(f"\n📚 {len(db_videos)} Videos in Database\n")
    print(f"{'ID':<15} {'Duration':<10} {'Has Summary':<12} {'Title'}")
    print("-" * 80)
    
    for v in db_videos:
        video_id = (v.id or 'N/A')[:12]
        duration = v.duration or 0
        duration_str = f"{int(duration/60)}m {int(duration%60)}s"
        has_summary = "✅" if v.summary_hi else "❌"
        title = (v.title_hi or v.title or 'N/A')[:40]
        print(f"{video_id:<15} {duration_str:<10} {has_summary:<12} {title}")
    
    print()


async def delete_video(video_id: str):
    """Delete a video from the DB."""
    factory = _get_session_factory()
    async with factory() as db:
        result = await crud.delete_video_db(db, video_id)
    
    if result:
        print(f"✅ Deleted: {video_id}")
    else:
        print(f"❌ Video not found: {video_id}")


async def main():
    # Initialize DB tables
    await init_db()
    
    parser = argparse.ArgumentParser(
        description="Admin tool for uploading and processing videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python admin_upload.py video.mp4                    # Process single video
    python admin_upload.py video.mp4 --audio            # Process with TTS audio
    python admin_upload.py --folder ./videos            # Process all in folder
    python admin_upload.py --list                       # List all videos
    python admin_upload.py --delete abc123              # Delete a video
    python admin_upload.py --regenerate abc123          # Regenerate summary
    python admin_upload.py --regenerate abc123 --audio  # Regenerate with audio
        """
    )
    
    parser.add_argument('file', nargs='?', help='Video/audio file to process')
    parser.add_argument('--folder', '-f', help='Process all files in folder')
    parser.add_argument('--list', '-l', action='store_true', help='List all videos')
    parser.add_argument('--delete', '-d', help='Delete a video by ID')
    parser.add_argument('--regenerate', '-r', help='Regenerate summary for video ID')
    parser.add_argument('--audio', '-a', action='store_true', help='Generate TTS audio')
    
    args = parser.parse_args()
    
    # List videos
    if args.list:
        await list_videos()
        return
    
    # Delete video
    if args.delete:
        await delete_video(args.delete)
        return
    
    # Regenerate
    if args.regenerate:
        await regenerate_content(args.regenerate, args.audio)
        return
    
    # Process folder
    if args.folder:
        folder_path = Path(args.folder)
        if not folder_path.exists():
            print(f"❌ Folder not found: {args.folder}")
            return
        await process_folder(folder_path, args.audio)
        return
    
    # Process single file
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"❌ File not found: {args.file}")
            return
        await process_video(file_path, args.audio)
        return
    
    # No arguments - show help
    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())

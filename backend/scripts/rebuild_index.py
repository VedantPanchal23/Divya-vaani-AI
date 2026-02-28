"""
Rebuild FAISS Index - Deduplicate & Optimize
This script:
1. Reads all transcript JSON files
2. Deduplicates by filename (keeps best version with most chunks)
3. Rebuilds the FAISS index from clean data
4. Rebuilds videos_content.json with proper titles

Run: cd backend && python scripts/rebuild_index.py
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

from config import settings


def get_clean_title(filename: str, full_text: str) -> str:
    """Extract a clean title from the filename or transcript text."""
    import re
    
    # Clean filename-based title
    name = Path(filename).stem
    
    # Remove UUID-like prefixes
    if re.match(r'^[a-f0-9]{8}-[a-f0-9]{3}$', name):
        # UUID-only filename, use first line of transcript
        first_line = full_text.strip().split('\n')[0][:100]
        # Clean up the first line
        first_line = re.sub(r'\s+', ' ', first_line).strip()
        if len(first_line) > 60:
            # Try to cut at a natural break
            cut = first_line[:60].rfind(' ')
            if cut > 30:
                first_line = first_line[:cut]
        return first_line + "..." if len(full_text) > 60 else first_line
    
    # Clean YouTube-style filenames
    # Remove " - ChannelName" suffix
    name = re.sub(r'\s*-\s*(?:Bhajan Marg|Sadhan Path|PremanandVicharOfficial|Shri Hit Premanand).*$', '', name, flags=re.IGNORECASE)
    
    # Remove underscores and clean formatting
    name = name.replace('_', ' ').strip()
    
    # Remove "MOTIVATIONAL VIDEO" and similar tags
    name = re.sub(r'\s*MOTIVATIONAL\s+VIDEO\s*', '', name, flags=re.IGNORECASE)
    
    # Clean multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    if not name or name == 'test' or name == 'maharaj-voice':
        # Fallback to transcript text
        first_line = full_text.strip()[:80]
        first_line = re.sub(r'\s+', ' ', first_line).strip()
        if len(first_line) > 60:
            cut = first_line[:60].rfind(' ')
            if cut > 30:
                first_line = first_line[:cut]
        return first_line + "..."
    
    return name


def deduplicate_transcripts():
    """Find unique transcripts by filename, keeping the best version."""
    transcript_dir = settings.TRANSCRIPT_DIR
    
    if not transcript_dir.exists():
        logger.error("No transcripts directory found")
        return []
    
    # Group by filename
    by_filename = defaultdict(list)
    
    for path in transcript_dir.glob("*.json"):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            filename = data.get("filename", path.stem)
            by_filename[filename].append({
                "path": path,
                "data": data,
                "chunk_count": len(data.get("chunks", [])),
                "text_length": len(data.get("full_text", ""))
            })
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
    
    # For each filename group, pick the best version (most chunks)
    unique_transcripts = []
    duplicates_found = 0
    
    for filename, versions in by_filename.items():
        versions.sort(key=lambda v: v["chunk_count"], reverse=True)
        best = versions[0]
        
        if len(versions) > 1:
            duplicates_found += len(versions) - 1
            logger.info(f"📋 '{filename}': {len(versions)} versions, keeping {best['data']['id']} ({best['chunk_count']} chunks)")
        
        unique_transcripts.append(best["data"])
    
    logger.info(f"\n📊 Stats:")
    logger.info(f"   Total transcript files: {sum(len(v) for v in by_filename.values())}")
    logger.info(f"   Unique content: {len(unique_transcripts)}")
    logger.info(f"   Duplicates found: {duplicates_found}")
    
    return unique_transcripts


def rebuild_faiss_index(transcripts: list):
    """Rebuild FAISS index from clean transcript data."""
    import numpy as np
    import faiss
    
    logger.info("\n🔨 Rebuilding FAISS index...")
    
    # Lazy load embedder
    from core.rag_engine import get_embedder, _embed_text
    
    all_meta = []
    all_embeddings = []
    
    for t_data in transcripts:
        transcript_id = t_data["id"]
        chunks = t_data.get("chunks", [])
        
        if not chunks:
            continue
        
        # Extract texts
        texts = [c["text"] for c in chunks if len(c.get("text", "").strip()) >= 20]
        
        if not texts:
            continue
        
        # Generate embeddings (as passages)
        embeddings = _embed_text(texts, is_query=False)
        
        # Build metadata
        text_idx = 0
        for c in chunks:
            if len(c.get("text", "").strip()) < 20:
                continue
            
            all_meta.append({
                "chunk_id": c["id"],
                "transcript_id": transcript_id,
                "text": c["text"],
                "start_time": c.get("start_time", 0.0),
                "end_time": c.get("end_time", 0.0)
            })
            text_idx += 1
        
        all_embeddings.append(embeddings)
        logger.info(f"   ✅ Indexed {len(texts)} chunks from {transcript_id}")
    
    if not all_embeddings:
        logger.error("No embeddings generated!")
        return
    
    # Combine all embeddings
    combined = np.vstack(all_embeddings)
    
    # Create FAISS index
    dim = combined.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(combined)
    
    # Save
    index_path = settings.INDEX_DIR / "transcripts.faiss"
    meta_path = settings.INDEX_DIR / "transcripts_meta.json"
    
    faiss.write_index(index, str(index_path))
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(all_meta, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n✅ FAISS index rebuilt:")
    logger.info(f"   Vectors: {index.ntotal}")
    logger.info(f"   Metadata entries: {len(all_meta)}")
    logger.info(f"   Dimension: {dim}")


def rebuild_videos_content(transcripts: list):
    """Rebuild videos_content.json from unique transcripts."""
    from data.videos_content import VideoContent, _save_videos_content
    
    logger.info("\n📹 Rebuilding videos_content.json...")
    
    videos = {}
    
    for t_data in transcripts:
        video_id = t_data["id"]
        filename = t_data.get("filename", "")
        full_text = t_data.get("full_text", "")
        
        # Generate clean title
        title = get_clean_title(filename, full_text)
        
        # Hindi title is the same since content is in Hindi
        title_hi = title
        
        # For English title, use filename if it has English
        import re
        has_english = bool(re.search(r'[a-zA-Z]{3,}', filename))
        title_en = title if has_english else f"Spiritual Discourse - {video_id[:8]}"
        
        video_content = VideoContent(
            id=video_id,
            title=title_en,
            title_hi=title_hi,
            description=f"Spiritual discourse. Duration: {int(t_data.get('duration', 0) / 60)} minutes.",
            description_hi="महाराज जी का आध्यात्मिक प्रवचन",
            thumbnail=f"/api/thumbnail/{video_id}",
            duration=t_data.get("duration", 0),
            transcript=full_text,
            transcript_chunks=t_data.get("chunks", []),
            summary_hi="",
            summary_en="",
            explanation_hi="",
            explanation_en="",
            created_at=t_data.get("created_at", datetime.now().isoformat()),
            category="pravachan",
            speaker="Maharaj Ji",
            tags=["प्रवचन", "आध्यात्मिक", "spiritual"]
        )
        
        videos[video_id] = video_content
        logger.info(f"   📹 {video_id}: {title[:60]}...")
    
    _save_videos_content(videos)
    logger.info(f"\n✅ videos_content.json rebuilt with {len(videos)} videos")


def main():
    print("\n" + "=" * 60)
    print("  Divya Vaani AI - Index Rebuild & Deduplication")
    print("=" * 60 + "\n")
    
    # Step 1: Get unique transcripts
    unique_transcripts = deduplicate_transcripts()
    
    if not unique_transcripts:
        logger.error("No transcripts found!")
        return
    
    # Step 2: Rebuild videos_content.json
    rebuild_videos_content(unique_transcripts)
    
    # Step 3: Rebuild FAISS index
    try:
        rebuild_faiss_index(unique_transcripts)
    except Exception as e:
        logger.error(f"FAISS rebuild failed: {e}")
        logger.info("You can still use the system - existing index will be used")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("  ✅ Rebuild Complete!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

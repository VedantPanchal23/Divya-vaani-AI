"""
Divya Vaani AI - RAG Engine
FAISS-based semantic search for transcripts and Bhagavad Gita.
"""
import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
import faiss

from config import settings
from data.schema import TranscriptChunk, GitaVerse, Transcript

logger = logging.getLogger(__name__)

# Global state
_embedder = None
_transcript_index = None
_transcript_meta = []
_gita_index = None
_gita_verses = []


def get_embedder():
    """Get sentence transformer model."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading {settings.EMBEDDING_MODEL}...")
        _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("✅ Embedder loaded")
    return _embedder


def _embed_text(texts: list, is_query: bool = False) -> np.ndarray:
    """
    Embed texts with proper prefix for E5 models.
    E5 models require 'query: ' prefix for queries and 'passage: ' for documents.
    """
    embedder = get_embedder()
    
    # Check if using E5 model (requires prefixes)
    is_e5 = "e5" in settings.EMBEDDING_MODEL.lower()
    
    if is_e5:
        prefix = "query: " if is_query else "passage: "
        texts = [prefix + t for t in texts]
    
    embeddings = embedder.encode(texts, convert_to_numpy=True)
    return _normalize(embeddings.astype("float32"))


def _normalize(vectors: np.ndarray) -> np.ndarray:
    """L2 normalize vectors for cosine similarity."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


# ========== Transcript Index ==========

def index_transcript(transcript: Transcript):
    """Add transcript chunks to the index."""
    global _transcript_index, _transcript_meta
    
    if not transcript.chunks:
        return
    
    _load_transcript_index()
    
    # Embed chunks (as passages, not queries)
    texts = [c.text for c in transcript.chunks]
    embeddings = _embed_text(texts, is_query=False)
    
    # Add to index
    _transcript_index.add(embeddings)
    
    # Store metadata
    for chunk in transcript.chunks:
        _transcript_meta.append({
            "chunk_id": chunk.id,
            "transcript_id": transcript.id,
            "text": chunk.text,
            "start_time": chunk.start_time,
            "end_time": chunk.end_time
        })
    
    # Save
    _save_transcript_index()
    logger.info(f"📚 Indexed {len(texts)} chunks from {transcript.filename}")


def search_transcripts(query: str, transcript_id: str = None, top_k: int = 10) -> List[TranscriptChunk]:
    """
    Search transcripts for relevant chunks.
    
    Uses semantic similarity to find chunks from spiritual discourses
    that are relevant to the user's question.
    
    Deduplicates results to avoid returning near-identical text from
    duplicate transcript entries.
    """
    global _transcript_meta
    
    _load_transcript_index()
    
    if _transcript_index.ntotal == 0:
        return []
    
    # Embed query (with query prefix for E5)
    q_emb = _embed_text([query], is_query=True)
    
    # If filtering by transcript_id, search more aggressively
    # because we need to find results in that specific transcript
    if transcript_id:
        k = min(500, _transcript_index.ntotal)  # Search more when filtering
    else:
        k = min(top_k * 10, _transcript_index.ntotal)  # Search more to deduplicate
    
    scores, indices = _transcript_index.search(q_emb, k)
    
    results = []
    seen_texts = set()  # Deduplicate by text content
    seen_time_windows = {}  # Track time windows per transcript to ensure diversity
    
    for i, idx in enumerate(indices[0]):
        if idx < 0 or idx >= len(_transcript_meta):
            continue
        
        meta = _transcript_meta[idx]
        
        # Filter by transcript_id if specified
        if transcript_id and meta["transcript_id"] != transcript_id:
            continue
        
        score = float(scores[0][i])
        
        # Use a very low threshold - we want to find ANY relevant content
        # The LLM will determine what's actually useful
        if score < settings.SIMILARITY_THRESHOLD:
            continue
        
        # Skip very short chunks (less meaningful)
        text = meta["text"].strip()
        if len(text) < 20:
            continue
        
        # Skip chunks that are mostly garbled/repetitive transcription
        # (e.g., "धर्म, धर्म, धर्म..." or chunks with too many commas relative to words)
        words = text.split()
        if len(words) > 3:
            unique_words = set(w.strip('.,।') for w in words if len(w.strip('.,।')) > 1)
            # If less than 40% unique words, it's likely repetitive/garbled
            if len(unique_words) / len(words) < 0.4:
                continue
        
        # Deduplicate: skip if we already have very similar text
        # Use first 60 chars as dedup key (catches duplicates from re-transcription)
        dedup_key = text[:60].lower().strip()
        if dedup_key in seen_texts:
            continue
        seen_texts.add(dedup_key)
        
        # Diversity filter: avoid multiple chunks from same 2-minute window 
        # in the same transcript (they often say the same thing)
        tid = meta["transcript_id"]
        start = meta.get("start_time", 0)
        time_bucket = int(start / 120)  # 2-minute windows
        bucket_key = f"{tid}_{time_bucket}"
        
        if bucket_key in seen_time_windows:
            # Already have a chunk from this time window in this transcript
            # Allow max 2 from same window, skip beyond that
            if seen_time_windows[bucket_key] >= 2:
                continue
        seen_time_windows[bucket_key] = seen_time_windows.get(bucket_key, 0) + 1
        
        results.append(TranscriptChunk(
            id=meta["chunk_id"],
            text=text,
            start_time=meta["start_time"],
            end_time=meta["end_time"]
        ))
        
        if len(results) >= top_k:
            break
    
    return results


def _load_transcript_index():
    """Load or create transcript index."""
    global _transcript_index, _transcript_meta
    
    if _transcript_index is not None:
        return
    
    index_path = settings.INDEX_DIR / "transcripts.faiss"
    meta_path = settings.INDEX_DIR / "transcripts_meta.json"
    
    if index_path.exists() and meta_path.exists():
        _transcript_index = faiss.read_index(str(index_path))
        with open(meta_path, "r", encoding="utf-8") as f:
            _transcript_meta = json.load(f)
        logger.info(f"📚 Loaded transcript index: {_transcript_index.ntotal} vectors")
    else:
        _transcript_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
        _transcript_meta = []
        logger.info("📚 Created new transcript index")


def _save_transcript_index():
    """Save transcript index to disk."""
    global _transcript_index, _transcript_meta
    
    if _transcript_index is None:
        return
    
    index_path = settings.INDEX_DIR / "transcripts.faiss"
    meta_path = settings.INDEX_DIR / "transcripts_meta.json"
    
    faiss.write_index(_transcript_index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(_transcript_meta, f, ensure_ascii=False, indent=2)


# ========== Bhagavad Gita Index ==========

def load_gita():
    """Load and index Bhagavad Gita verses."""
    global _gita_index, _gita_verses
    
    if _gita_index is not None:
        return
    
    index_path = settings.INDEX_DIR / "gita.faiss"
    
    if index_path.exists():
        _gita_index = faiss.read_index(str(index_path))
        _load_gita_verses()
        logger.info(f"📖 Loaded Gita index: {_gita_index.ntotal} verses")
        return
    
    # Load from JSON and index
    if not settings.GITA_PATH.exists():
        logger.warning("⚠️ bhagavad_gita.json not found")
        _gita_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
        _gita_verses = []
        return
    
    with open(settings.GITA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    _gita_verses = data.get("verses", [])
    
    if not _gita_verses:
        _gita_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
        return
    
    # Create embeddings (as passages)
    texts = [f"{v['hindi_meaning']} {v['english_meaning']}" for v in _gita_verses]
    embeddings = _embed_text(texts, is_query=False)
    
    # Create index
    _gita_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
    _gita_index.add(embeddings)
    
    # Save
    faiss.write_index(_gita_index, str(index_path))
    logger.info(f"📖 Indexed {len(_gita_verses)} Gita verses")


def _load_gita_verses():
    """Load Gita verses from JSON."""
    global _gita_verses
    
    if not settings.GITA_PATH.exists():
        _gita_verses = []
        return
    
    with open(settings.GITA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    _gita_verses = data.get("verses", [])


def search_gita(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Search Bhagavad Gita for relevant verses."""
    global _gita_index, _gita_verses
    
    load_gita()
    
    if _gita_index is None or _gita_index.ntotal == 0:
        return []
    
    # Embed query (with query prefix for E5)
    q_emb = _embed_text([query], is_query=True)
    
    # Search
    k = min(top_k, _gita_index.ntotal)
    scores, indices = _gita_index.search(q_emb, k)
    
    results = []
    for i, idx in enumerate(indices[0]):
        if idx < 0 or idx >= len(_gita_verses):
            continue
        
        score = float(scores[0][i])
        if score < settings.SIMILARITY_THRESHOLD:
            continue
        
        verse = _gita_verses[idx]
        results.append({
            "verse": GitaVerse(
                chapter=verse["chapter"],
                verse=verse["verse"],
                sanskrit=verse.get("sanskrit", ""),
                hindi=verse.get("hindi_meaning", ""),
                english=verse.get("english_meaning", "")
            ),
            "score": score
        })
    
    return results


def has_transcripts() -> bool:
    """Check if any transcripts are indexed."""
    _load_transcript_index()
    return _transcript_index.ntotal > 0

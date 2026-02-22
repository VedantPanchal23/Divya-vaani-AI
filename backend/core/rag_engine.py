"""
Divya Vaani AI - RAG Engine (Production Grade)
Hybrid search (semantic + keyword) with re-ranking for transcripts and Bhagavad Gita.
"""
import json
import logging
import re
import math
import threading
import numpy as np
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    import faiss
except ImportError:
    faiss = None
    logging.getLogger(__name__).warning("faiss-cpu not installed — RAG search disabled")

from config import settings
from data.schema import TranscriptChunk, GitaVerse, Transcript

logger = logging.getLogger(__name__)

# Global state
_embedder = None
_transcript_index = None
_transcript_meta = []
_gita_index = None
_gita_verses = []

# Thread safety locks
_transcript_lock = threading.Lock()
_gita_lock = threading.Lock()
_embedder_lock = threading.Lock()


def get_embedder():
    """Get sentence transformer model (thread-safe)."""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:  # double-check
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading {settings.EMBEDDING_MODEL}...")
                _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
                logger.info("Embedder loaded successfully")
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


# ========== Keyword Search (BM25-style) ==========

# Hindi stop words to exclude from keyword matching
_HINDI_STOP_WORDS = {
    "है", "हैं", "था", "थी", "थे", "हो", "होता", "होती", "होते",
    "का", "के", "की", "को", "से", "में", "पर", "ने", "और", "या",
    "एक", "यह", "वह", "जो", "कि", "तो", "भी", "ही", "इस", "उस",
    "कर", "करता", "करती", "करते", "कोई", "कुछ", "सब", "बहुत",
    "अपने", "अपना", "अपनी", "मेरा", "मेरी", "मेरे", "तुम",
    "हमारा", "हमारी", "हमारे", "आप", "मैं", "हम", "वो",
    "क्या", "कैसे", "क्यों", "कब", "कहाँ", "कहां", "कौन",
    "नहीं", "मत", "ना", "बिना", "लिए", "लिये", "साथ",
    "रहा", "रही", "रहे", "गया", "गयी", "गये", "गए",
    "the", "is", "are", "was", "were", "be", "been", "being",
    "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "it", "this", "that", "what",
    "how", "why", "when", "where", "who", "which", "do", "does",
    "did", "has", "have", "had", "will", "would", "can", "could",
    "not", "no", "if", "about", "me", "my", "i", "we", "you",
}

# Spiritual domain vocabulary — these terms get bonus weight in keyword matching
_SPIRITUAL_TERMS = {
    "भक्ति", "भगवान", "प्रेम", "सेवा", "कृपा", "धर्म", "कर्म",
    "ज्ञान", "वैराग्य", "मोक्ष", "मुक्ति", "साधना", "ध्यान",
    "श्रद्धा", "संसार", "माया", "जीव", "आत्मा", "परमात्मा",
    "गुरु", "महाराज", "प्रवचन", "शरणागति", "भजन", "कीर्तन",
    "राधा", "कृष्ण", "गोपी", "ब्रज", "वृन्दावन", "वृंदावन",
    "धैर्य", "विपत्ति", "परेशान", "शांति", "आनंद", "दया",
    "क्षमा", "त्याग", "तप", "संयम", "विश्वास", "निष्ठा",
    "devotion", "god", "love", "service", "grace", "dharma", "karma",
    "knowledge", "detachment", "liberation", "meditation", "faith",
    "soul", "spiritual", "peace", "patience", "forgiveness",
}


def _tokenize_hindi(text: str) -> List[str]:
    """Tokenize Hindi/English text into meaningful terms."""
    # Lowercase for English, keep Hindi as-is
    text_lower = text.lower()
    # Split on non-alphanumeric (respecting Devanagari range)
    tokens = re.findall(r'[\u0900-\u097F]+|[a-z]+', text_lower)
    # Remove stop words and very short tokens
    return [t for t in tokens if t not in _HINDI_STOP_WORDS and len(t) > 1]


def _compute_keyword_score(query_tokens: List[str], doc_text: str) -> float:
    """
    Compute a keyword-based relevance score between query tokens and a document.
    Uses TF-based scoring with spiritual term boosting.
    Returns a score between 0.0 and 1.0.
    """
    if not query_tokens:
        return 0.0
    
    doc_tokens = _tokenize_hindi(doc_text)
    if not doc_tokens:
        return 0.0
    
    doc_token_counts = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    
    total_score = 0.0
    matched_terms = 0
    
    for qt in query_tokens:
        if qt in doc_token_counts:
            matched_terms += 1
            # TF component: log(1 + count/doc_len)
            tf = math.log(1 + doc_token_counts[qt] / max(doc_len, 1))
            # Boost spiritual terms
            boost = 1.5 if qt in _SPIRITUAL_TERMS else 1.0
            total_score += tf * boost
        else:
            # Check for substring match (partial Hindi word matching)
            for dt in doc_token_counts:
                if len(qt) >= 3 and (qt in dt or dt in qt):
                    matched_terms += 0.5
                    tf = math.log(1 + doc_token_counts[dt] / max(doc_len, 1)) * 0.5
                    total_score += tf
                    break
    
    # Coverage: what fraction of query terms were found
    coverage = matched_terms / len(query_tokens)
    
    # Combine: weighted sum of coverage and TF score
    # Normalize TF score by number of query tokens
    normalized_tf = total_score / len(query_tokens)
    
    # Final score: coverage is more important than raw TF
    score = 0.6 * coverage + 0.4 * min(normalized_tf, 1.0)
    
    return min(score, 1.0)


def search_transcripts_keyword(
    query: str, transcript_id: str = None, top_k: int = 10
) -> List[dict]:
    """
    Search transcripts using keyword matching (BM25-style).
    Useful for exact Hindi term matching that semantic search might miss.
    Returns list of {"chunk": TranscriptChunk, "score": float}
    """
    with _transcript_lock:
        _load_transcript_index()
        
        if not _transcript_meta:
            return []
    
    query_tokens = _tokenize_hindi(query)
    if not query_tokens:
        return []
    
    scored_results = []
    
    for meta in _transcript_meta:
        # Filter by transcript_id if specified
        if transcript_id and meta["transcript_id"] != transcript_id:
            continue
        
        # Skip very short chunks
        if len(meta["text"].strip()) < 20:
            continue
        
        score = _compute_keyword_score(query_tokens, meta["text"])
        
        if score > 0.15:  # Minimum keyword relevance threshold
            scored_results.append({
                "chunk": TranscriptChunk(
                    id=meta["chunk_id"],
                    text=meta["text"],
                    start_time=meta["start_time"],
                    end_time=meta["end_time"]
                ),
                "score": score,
                "meta": meta
            })
    
    # Sort by score descending
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    
    # Return top_k, dropping internal 'meta' key
    return [{"chunk": r["chunk"], "score": r["score"]} for r in scored_results[:top_k]]


# ========== Hybrid Search with Reciprocal Rank Fusion ==========

def search_transcripts_hybrid(
    query: str,
    transcript_id: str = None,
    top_k: int = 8,
    semantic_weight: float = 0.65,
    keyword_weight: float = 0.35,
    semantic_min_score: Optional[float] = None,
) -> List[dict]:
    """
    Hybrid search combining semantic (FAISS) and keyword (BM25-style) results.
    Uses Reciprocal Rank Fusion (RRF) to merge ranked lists.
    
    Returns list of {"chunk": TranscriptChunk, "score": float, "semantic_score": float, "keyword_score": float}
    """
    # Get semantic results (more candidates for fusion)
    semantic_results = search_transcripts_with_scores(
        query,
        transcript_id,
        top_k=top_k * 2,
        min_score=semantic_min_score,
    )
    
    # Get keyword results
    keyword_results = search_transcripts_keyword(query, transcript_id, top_k=top_k * 2)
    
    if not semantic_results and not keyword_results:
        return []
    
    # RRF constant (standard value)
    k = 60
    
    # Build RRF scores keyed by chunk_id
    rrf_scores = defaultdict(lambda: {"rrf": 0.0, "chunk": None, "semantic_score": 0.0, "keyword_score": 0.0})
    
    for rank, result in enumerate(semantic_results):
        chunk_id = result["chunk"].id
        rrf_scores[chunk_id]["rrf"] += semantic_weight * (1.0 / (k + rank + 1))
        rrf_scores[chunk_id]["chunk"] = result["chunk"]
        rrf_scores[chunk_id]["semantic_score"] = result["score"]
    
    for rank, result in enumerate(keyword_results):
        chunk_id = result["chunk"].id
        rrf_scores[chunk_id]["rrf"] += keyword_weight * (1.0 / (k + rank + 1))
        if rrf_scores[chunk_id]["chunk"] is None:
            rrf_scores[chunk_id]["chunk"] = result["chunk"]
        rrf_scores[chunk_id]["keyword_score"] = result["score"]
    
    # Sort by RRF score
    merged = sorted(rrf_scores.values(), key=lambda x: x["rrf"], reverse=True)
    
    # Build final results
    results = []
    for item in merged[:top_k]:
        if item["chunk"] is None:
            continue
        
        # Combined score for display (higher of the two individual scores, weighted)
        combined_score = max(
            item["semantic_score"],
            item["keyword_score"] * 0.85  # Slight discount for keyword-only matches
        )
        
        results.append({
            "chunk": item["chunk"],
            "score": combined_score,
            "semantic_score": item["semantic_score"],
            "keyword_score": item["keyword_score"],
            "rrf_score": item["rrf"],
        })
    
    logger.debug(
        f"Hybrid search: {len(semantic_results)} semantic + {len(keyword_results)} keyword "
        f"-> {len(results)} merged results"
    )
    
    return results


# ========== Transcript Index ==========

def index_transcript(transcript: Transcript):
    """Add transcript chunks to the index (with duplicate detection, thread-safe)."""
    global _transcript_index, _transcript_meta
    
    if not transcript.chunks:
        return
    
    with _transcript_lock:
        _load_transcript_index()
        
        # Check for duplicate transcript — remove old entries before re-indexing
        existing_ids = {m["transcript_id"] for m in _transcript_meta}
        if transcript.id in existing_ids:
            logger.info(f"Transcript {transcript.id} already indexed — removing old entries before re-indexing")
            _remove_transcript_from_index(transcript.id)
        
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
        logger.info(f"Indexed {len(texts)} chunks from {transcript.filename}")


def _remove_transcript_from_index(transcript_id: str):
    """Remove all entries for a transcript and rebuild the FAISS index."""
    global _transcript_index, _transcript_meta
    
    # Filter out old entries
    new_meta = [m for m in _transcript_meta if m["transcript_id"] != transcript_id]
    removed_count = len(_transcript_meta) - len(new_meta)
    
    if removed_count == 0:
        return
    
    # Rebuild index from remaining metadata
    _transcript_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
    
    if new_meta:
        texts = [m["text"] for m in new_meta]
        embeddings = _embed_text(texts, is_query=False)
        _transcript_index.add(embeddings)
    
    _transcript_meta = new_meta
    logger.info(f"Removed {removed_count} old entries for transcript {transcript_id}")


def search_transcripts(
    query: str,
    transcript_id: str = None,
    top_k: int = 10,
    min_score: Optional[float] = None,
) -> List[TranscriptChunk]:
    """
    Search transcripts for relevant chunks.
    Uses semantic similarity to find chunks from spiritual discourses.
    """
    results = search_transcripts_with_scores(
        query, transcript_id, top_k, min_score=min_score
    )
    return [r["chunk"] for r in results]


def search_transcripts_with_scores(
    query: str,
    transcript_id: str = None,
    top_k: int = 10,
    min_score: Optional[float] = None,
) -> List[dict]:
    """
    Search transcripts and return chunks WITH their similarity scores.
    Returns list of {"chunk": TranscriptChunk, "score": float}
    """
    global _transcript_meta
    
    threshold = settings.SIMILARITY_THRESHOLD if min_score is None else float(min_score)

    # Load index (if not loaded yet)
    with _transcript_lock:
        _load_transcript_index()
        
        if _transcript_index.ntotal == 0:
            logger.warning("[Search] Transcript index is empty (0 vectors)")
            return []
        
        index_total = _transcript_index.ntotal
    
    # Embed query OUTSIDE the lock — this is the slow step (27s on CPU)
    q_emb = _embed_text([query], is_query=True)
    
    with _transcript_lock:
        # If filtering by transcript_id, search more aggressively
        if transcript_id:
            k = min(500, _transcript_index.ntotal)
        else:
            k = min(top_k * 5, _transcript_index.ntotal)
        
        scores, indices = _transcript_index.search(q_emb, k)
        
        results = []
        seen_texts = set()  # De-duplicate near-identical chunks
        skipped_tid = 0
        skipped_threshold = 0
        skipped_short = 0
        
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(_transcript_meta):
                continue
            
            meta = _transcript_meta[idx]
            
            # Filter by transcript_id if specified
            if transcript_id and meta["transcript_id"] != transcript_id:
                skipped_tid += 1
                continue
            
            score = float(scores[0][i])
            
            if score < threshold:
                skipped_threshold += 1
                continue
            
            # Skip very short chunks (less meaningful)
            text = meta["text"].strip()
            if len(text) < 20:
                skipped_short += 1
                continue
            
            # De-duplicate: skip if we already have a very similar chunk
            text_key = text[:80]  # First 80 chars as dedup key
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)
            
            results.append({
                "chunk": TranscriptChunk(
                    id=meta["chunk_id"],
                    text=meta["text"],
                    start_time=meta["start_time"],
                    end_time=meta["end_time"]
                ),
                "score": score
            })
            
            if len(results) >= top_k:
                break
    
    # Diagnostic logging for zero-result searches
    if not results and transcript_id:
        # Count how many chunks exist for this transcript_id
        matching_chunks = sum(1 for m in _transcript_meta if m["transcript_id"] == transcript_id)
        top_raw = float(scores[0][0]) if scores is not None and len(scores[0]) > 0 else 0.0
        logger.warning(
            f"[Search] 0 results for tid={transcript_id} (query='{query[:50]}...'). "
            f"Index has {index_total} vectors, {matching_chunks} for this tid. "
            f"Skipped: tid_filter={skipped_tid}, threshold={skipped_threshold}, short={skipped_short}. "
            f"Top raw score={top_raw:.4f}, threshold={threshold}"
        )
    
    return results


def _load_transcript_index():
    """Load or create transcript index."""
    global _transcript_index, _transcript_meta
    
    if _transcript_index is not None:
        return
    
    index_path = settings.INDEX_DIR / "transcripts.faiss"
    meta_path = settings.INDEX_DIR / "transcripts_meta.json"
    
    if index_path.exists() and meta_path.exists():
        try:
            _transcript_index = faiss.read_index(str(index_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                _transcript_meta = json.load(f)
            logger.info(f"Loaded transcript index: {_transcript_index.ntotal} vectors")
        except Exception as e:
            logger.error(f"Failed to load transcript index (corrupted?): {e}")
            logger.info("Creating fresh transcript index")
            _transcript_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
            _transcript_meta = []
    else:
        _transcript_index = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
        _transcript_meta = []
        logger.info("Created new transcript index")


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
        try:
            _gita_index = faiss.read_index(str(index_path))
            _load_gita_verses()
            logger.info(f"Loaded Gita index: {_gita_index.ntotal} verses")
            return
        except Exception as e:
            logger.error(f"Failed to load Gita index (corrupted?): {e}")
            logger.info("Rebuilding Gita index...")
    
    # Load from JSON and index
    if not settings.GITA_PATH.exists():
        logger.warning("bhagavad_gita.json not found")
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
    logger.info(f"Indexed {len(_gita_verses)} Gita verses")


def _load_gita_verses():
    """Load Gita verses from JSON."""
    global _gita_verses
    
    if not settings.GITA_PATH.exists():
        _gita_verses = []
        return
    
    with open(settings.GITA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    _gita_verses = data.get("verses", [])


def search_gita(query: str, top_k: int = 3, threshold: float = None) -> List[Dict[str, Any]]:
    """Search Bhagavad Gita for relevant verses (thread-safe)."""
    global _gita_index, _gita_verses
    
    if threshold is None:
        threshold = settings.GITA_FALLBACK_THRESHOLD
    
    with _gita_lock:
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
            if score < threshold:
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
    with _transcript_lock:
        _load_transcript_index()
        return _transcript_index.ntotal > 0


def get_transcript_count() -> int:
    """Get the total number of indexed transcript chunks."""
    with _transcript_lock:
        _load_transcript_index()
        return _transcript_index.ntotal

# -*- coding: utf-8 -*-
"""Test: simulate the exact query flow from chat_routes to see why 0 results."""
import sys, json
sys.path.insert(0, '.')
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)

from config import settings
from core import rag_engine

# Load index
rag_engine._load_transcript_index()
print(f"Index: {rag_engine._transcript_index.ntotal} vectors, threshold={settings.SIMILARITY_THRESHOLD}")

question = "how can i control my brain?"
content_id = "3456820f-613"

# Step 1: Direct raw search (what debug did)
results_raw = rag_engine.search_transcripts_with_scores(question, transcript_id=content_id, top_k=8)
print(f"\n1. RAW query '{question}': {len(results_raw)} results")
for r in results_raw[:3]:
    print(f"   score={r['score']:.4f} | {r['chunk'].text[:60]}")

# Step 2: With Hindi translation appended
search_query = f"{question} mein man ko kaise niyantrit kiya jaaye"
results_translated = rag_engine.search_transcripts_with_scores(search_query, transcript_id=content_id, top_k=8)
print(f"\n2. TRANSLATED query: {len(results_translated)} results")
for r in results_translated[:3]:
    print(f"   score={r['score']:.4f} | {r['chunk'].text[:60]}")

# Step 3: Hybrid search
print(f"\n3. HYBRID search (HYBRID_SEARCH_ENABLED={settings.HYBRID_SEARCH_ENABLED}):")
if settings.HYBRID_SEARCH_ENABLED:
    results_hybrid = rag_engine.search_transcripts_hybrid(question, transcript_id=content_id, top_k=8)
    print(f"   {len(results_hybrid)} results")
    for r in results_hybrid[:3]:
        print(f"   score={r['score']:.4f} sem={r.get('semantic_score',0):.4f} kw={r.get('keyword_score',0):.4f} | {r['chunk'].text[:60]}")
else:
    print("   DISABLED - using semantic only")

# Step 4: Check if has_transcripts works
print(f"\n4. has_transcripts()={rag_engine.has_transcripts()}")

# Step 5: Check content_id matching
print(f"\n5. Checking content_id filtering for '{content_id}':")
matching_meta = [m for m in rag_engine._transcript_meta if m["transcript_id"] == content_id]
print(f"   Exact matches: {len(matching_meta)}")
if not matching_meta:
    partial = [m for m in rag_engine._transcript_meta if content_id in m["transcript_id"]]
    print(f"   Partial matches: {len(partial)}")
    if partial:
        print(f"   Full tid: {partial[0]['transcript_id']}")

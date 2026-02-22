import json, urllib.request, time

BASE = "http://localhost:8000"

def post(path, body):
    req = urllib.request.Request(
        f"{BASE}{path}",
        json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req, timeout=180).read())

# Get first video
r = urllib.request.urlopen(f"{BASE}/api/videos", timeout=10)
data = json.loads(r.read())
videos = data if isinstance(data, list) else data.get("videos", [])
vid = str(videos[0].get("id", videos[0].get("video_id", "")))
print(f"Video: {vid}")

# First call (will be slow - embeddings + LLM)
t0 = time.time()
r1 = post("/api/chat", {"question": "What is the main message?", "transcript_id": vid, "language": "en"})
t1 = time.time() - t0
print(f"FIRST CALL:  src={r1['source_type']}, time={t1:.2f}s, answer_len={len(r1['answer'])}")

# Second call (should be cached)
t0 = time.time()
r2 = post("/api/chat", {"question": "What is the main message?", "transcript_id": vid, "language": "en"})
t2 = time.time() - t0
print(f"CACHED CALL: src={r2['source_type']}, time={t2:.2f}s, answer_len={len(r2['answer'])}")

if t2 < 1.0:
    print(f"CACHE PASS: {t2:.2f}s << {t1:.2f}s (speedup {t1/max(t2,0.001):.0f}x)")
else:
    print(f"CACHE MAYBE: {t2:.2f}s vs {t1:.2f}s")

# Gita explicit with smarter threshold
t0 = time.time()
r3 = post("/api/chat", {"question": "What does Bhagavad Gita say about duty?", "language": "en"})
t3 = time.time() - t0
src_ref = r3.get("source_reference", "")
print(f"GITA: src={r3['source_type']}, ref={src_ref[:80]}, time={t3:.2f}s")

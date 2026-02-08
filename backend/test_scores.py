from core.rag_engine import search_transcripts_with_scores, search_gita

query = "गीता में कर्मयोग क्या है?"

print(f"Query: {query}\n")

# Check keyword detection
gita_keywords_hi = ["गीता", "अर्जुन", "भगवद", "श्लोक", "अध्याय"]
is_gita = any(kw in query for kw in gita_keywords_hi)
print(f"Is Gita question: {is_gita}")
print(f"Keyword matches: {[kw for kw in gita_keywords_hi if kw in query]}")
print()

results = search_transcripts_with_scores(query, top_k=3)
print("Transcript scores:")
for r in results:
    print(f"  Score: {r['score']:.3f} - {r['chunk'].text[:60]}...")

print()

gita = search_gita(query, top_k=3)
print("Gita scores:")
for g in gita:
    print(f"  Score: {g['score']:.3f} - Ch{g['verse'].chapter}:{g['verse'].verse}")

print()
print(f"Best transcript: {results[0]['score']:.3f}" if results else "No transcript results")
print(f"Best gita: {gita[0]['score']:.3f}" if gita else "No gita results")

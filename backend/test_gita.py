import warnings
warnings.filterwarnings("ignore")

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

try:
    from core.rag_engine import load_gita, search_gita

    print("Loading Gita...")
    load_gita()
    print("Searching for 'how to control anger'...")
    results = search_gita("how to control anger", top_k=3)

    print(f"\nFound {len(results)} verses:\n")
    for r in results:
        v = r["verse"]
        score = r["score"]
        print(f"Chapter {v.chapter}, Verse {v.verse} (Score: {score:.3f})")
        print(f"Hindi: {v.hindi[:100]}...")
        print()
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Error: {e}")

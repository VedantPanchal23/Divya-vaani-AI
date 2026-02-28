"""
Generate summaries and explanations for all videos that don't have them.
Uses Gemini API for fast generation.
"""
import sys, os, asyncio, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from data.videos_content import _load_videos_content, update_video_content
from core.llm_engine import generate_summary, generate_explanation

async def main():
    videos = _load_videos_content()
    print(f"Found {len(videos)} videos")
    
    for vid_id, vid in videos.items():
        needs_summary = not vid.summary_hi or not vid.summary_en
        needs_explanation = not vid.explanation_hi or not vid.explanation_en
        
        if not needs_summary and not needs_explanation:
            print(f"  SKIP {vid_id}: already has content")
            continue
        
        transcript = vid.transcript
        if not transcript or len(transcript) < 50:
            print(f"  SKIP {vid_id}: no transcript")
            continue
        
        # Use only first 3000 chars to keep API costs down
        text = transcript[:3000]
        print(f"\n  Processing {vid_id} ({len(transcript)} chars)...")
        
        updates = {}
        
        if needs_summary:
            try:
                print(f"    Generating Hindi summary...")
                summary_hi = await generate_summary(text, "hi")
                print(f"    Generating English summary...")
                summary_en = await generate_summary(text, "en")
                updates["summary_hi"] = summary_hi
                updates["summary_en"] = summary_en
                print(f"    ✅ Summaries: {len(summary_hi)} / {len(summary_en)} chars")
            except Exception as e:
                print(f"    ❌ Summary failed: {e}")
        
        if needs_explanation:
            try:
                print(f"    Generating Hindi explanation...")
                explanation_hi = await generate_explanation(text, "hi")
                print(f"    Generating English explanation...")
                explanation_en = await generate_explanation(text, "en")
                updates["explanation_hi"] = explanation_hi
                updates["explanation_en"] = explanation_en
                print(f"    ✅ Explanations: {len(explanation_hi)} / {len(explanation_en)} chars")
            except Exception as e:
                print(f"    ❌ Explanation failed: {e}")
        
        if updates:
            update_video_content(vid_id, updates)
            print(f"    💾 Saved updates for {vid_id}")
    
    print("\n✅ Done!")

if __name__ == "__main__":
    asyncio.run(main())

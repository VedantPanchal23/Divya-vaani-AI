"""
Script to generate LLM summaries and themes for pravachan videos.
Adds 'themes', 'summary', and 'main_topic' fields to videos_content.json
Uses Groq API for generation.
"""

import json
import os
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from groq import Groq


def get_groq_client():
    """Initialize Groq client."""
    return Groq(api_key=settings.GROQ_API_KEY.get_secret_value())


def generate_video_metadata(transcript: str, client) -> dict:
    """Generate summary, themes, and main topic from transcript."""
    
    # Truncate transcript if too long (Groq has token limits - use smaller chunk)
    max_chars = 8000
    truncated_transcript = transcript[:max_chars] if len(transcript) > max_chars else transcript
    
    prompt = f"""Analyze this Hindi spiritual discourse (pravachan) transcript and extract:

1. **main_topic** (string): The primary topic discussed in 5-10 words (in Hindi)
2. **main_topic_en** (string): Same topic in English
3. **summary** (string): A 2-3 sentence summary of the main message (in Hindi)
4. **summary_en** (string): Same summary in English
5. **themes** (array): List of 3-6 key themes/topics discussed (in Hindi)
6. **themes_en** (array): Same themes in English
7. **key_teachings** (array): 2-4 practical teachings or takeaways (in Hindi)

IMPORTANT: 
- Focus on the actual spiritual content, not the chanting parts (राधा राधा etc.)
- Identify the core teachings of Maharaj Ji
- Be concise and specific

Return ONLY valid JSON in this exact format:
{{
    "main_topic": "...",
    "main_topic_en": "...",
    "summary": "...",
    "summary_en": "...",
    "themes": ["theme1", "theme2", ...],
    "themes_en": ["theme1", "theme2", ...],
    "key_teachings": ["teaching1", "teaching2", ...]
}}

TRANSCRIPT:
{truncated_transcript}
"""
    
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes Hindi spiritual discourses and returns JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        text = response.choices[0].message.content.strip()
        
        # Clean up response - remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        # Parse JSON
        metadata = json.loads(text)
        return metadata
    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON parse error: {e}")
        print(f"  Raw response: {text[:500]}...")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def main():
    # Paths
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    videos_file = os.path.join(data_dir, 'videos_content.json')
    
    # Load existing videos
    print("📂 Loading videos_content.json...")
    with open(videos_file, 'r', encoding='utf-8') as f:
        videos = json.load(f)
    
    print(f"📹 Found {len(videos)} videos")
    
    # Initialize Groq
    print("🤖 Initializing Groq client...")
    client = get_groq_client()
    
    # Process each video
    updated_count = 0
    for video_id, video_data in videos.items():
        print(f"\n📍 Processing: {video_data.get('title', video_id)[:60]}...")
        
        # Skip if already has themes
        if video_data.get('themes') and video_data.get('summary'):
            print("  ✓ Already has metadata, skipping")
            continue
        
        transcript = video_data.get('transcript', '')
        if not transcript or len(transcript) < 100:
            print("  ⚠️ No transcript or too short, skipping")
            continue
        
        # Generate metadata
        print("  🔄 Generating summary and themes...")
        metadata = generate_video_metadata(transcript, client)
        
        if metadata:
            # Add metadata to video
            video_data['main_topic'] = metadata.get('main_topic', '')
            video_data['main_topic_en'] = metadata.get('main_topic_en', '')
            video_data['summary'] = metadata.get('summary', '')
            video_data['summary_en'] = metadata.get('summary_en', '')
            video_data['themes'] = metadata.get('themes', [])
            video_data['themes_en'] = metadata.get('themes_en', [])
            video_data['key_teachings'] = metadata.get('key_teachings', [])
            
            print(f"  ✅ Main topic: {metadata.get('main_topic', 'N/A')}")
            print(f"  ✅ Themes: {', '.join(metadata.get('themes', []))}")
            updated_count += 1
        else:
            print("  ❌ Failed to generate metadata")
        
        # Delay to avoid rate limits (Groq has 30 req/min on free tier)
        print("  ⏳ Waiting 3 seconds to avoid rate limits...")
        time.sleep(3)
    
    # Save updated videos
    print(f"\n💾 Saving updated videos_content.json...")
    with open(videos_file, 'w', encoding='utf-8') as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Done! Updated {updated_count} videos with summaries and themes")


if __name__ == "__main__":
    main()

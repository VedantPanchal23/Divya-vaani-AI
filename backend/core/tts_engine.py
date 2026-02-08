"""
Divya Vaani AI - TTS Engine v4.3 (ULTRA FAST)

Uses gTTS (Google TTS) as primary - much faster than Edge TTS.
Target: Under 2-3 seconds for any text.
LRU cache to prevent unbounded memory growth.
"""
import logging
import uuid
import asyncio
import re
import hashlib
from pathlib import Path
from typing import Optional
from collections import OrderedDict
import time

from config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

EDGE_TTS_VOICES = {
    "hi_male": "hi-IN-MadhurNeural",
    "hi_female": "hi-IN-SwaraNeural",
    "en_male": "en-IN-PrabhatNeural",
    "en_female": "en-IN-NeerjaNeural",
}

# SPEED: Aggressive text limit
MAX_TEXT_LENGTH = 150  # Very short for speed

# LRU Cache with max size
class _LRUCache(OrderedDict):
    def __init__(self, maxsize=500):
        super().__init__()
        self._maxsize = maxsize
    
    def get(self, key, default=None):
        if key in self:
            self.move_to_end(key)
            return self[key]
        return default
    
    def set(self, key, value):
        if key in self:
            self.move_to_end(key)
        self[key] = value
        if len(self) > self._maxsize:
            self.popitem(last=False)

_audio_cache = _LRUCache(maxsize=settings.TTS_CACHE_MAX_SIZE)


# =============================================================================
# Main TTS Function - ULTRA FAST
# =============================================================================

async def generate_speech_async(
    text: str, 
    language: str = "hi", 
    gender: str = None
) -> str:
    """
    Generate speech - ULTRA FAST mode.
    Uses gTTS (Google) as primary - much faster than Edge TTS.
    """
    if not text or not text.strip():
        return ""
    
    start_time = time.time()
    
    # Prepare text (truncate aggressively)
    clean_text = _prepare_text_fast(text, language)
    if not clean_text:
        return ""
    
    # Check cache
    cache_key = hashlib.md5(f"{clean_text}:{language}".encode()).hexdigest()[:12]
    cached = _audio_cache.get(cache_key)
    if cached:
        if (settings.AUDIO_DIR / cached.split('/')[-1]).exists():
            logger.info(f"Cache hit: {time.time()-start_time:.2f}s")
            return cached
    
    try:
        settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        
        audio_id = str(uuid.uuid4())[:8]
        filename = f"tts_{audio_id}.mp3"
        filepath = settings.AUDIO_DIR / filename
        
        # PRIMARY: Use gTTS (Google) - FASTER
        success = await _generate_gtts_fast(clean_text, language, filepath)
        
        if success:
            url = f"/api/audio/{filename}"
            _audio_cache.set(cache_key, url)
            elapsed = time.time() - start_time
            logger.info(f"TTS done: {elapsed:.2f}s ({len(clean_text)} chars)")
            return url
        
        # FALLBACK: Edge TTS
        logger.warning("gTTS failed, trying Edge TTS...")
        success = await _generate_edge_tts_fast(clean_text, language, gender or "male", filepath)
        
        if success:
            url = f"/api/audio/{filename}"
            _audio_cache.set(cache_key, url)
            return url
        
        return ""
        
    except Exception as e:
        logger.error(f"❌ TTS error: {e}")
        return ""


async def generate_long_speech_async(text: str, language: str = "hi", gender: str = None) -> str:
    return await generate_speech_async(text, language, gender)


# =============================================================================
# gTTS - FAST (Primary)
# =============================================================================

async def _generate_gtts_fast(text: str, language: str, output_path: Path) -> bool:
    """
    Generate using gTTS - FAST.
    Typically 1-2 seconds for short text.
    """
    try:
        from gtts import gTTS
        
        gtts_lang = "hi" if language == "hi" else "en"
        
        def generate():
            tts = gTTS(text=text, lang=gtts_lang, slow=False)
            tts.save(str(output_path))
            return output_path.exists() and output_path.stat().st_size > 0
        
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, generate),
            timeout=5.0  # 5 second timeout
        )
        return result
        
    except asyncio.TimeoutError:
        logger.error("❌ gTTS timeout")
        return False
    except Exception as e:
        logger.error(f"❌ gTTS error: {e}")
        return False


# =============================================================================
# Edge TTS - Backup
# =============================================================================

async def _generate_edge_tts_fast(text: str, language: str, gender: str, output_path: Path) -> bool:
    """Edge TTS as backup."""
    try:
        import edge_tts
        
        voice = EDGE_TTS_VOICES.get(f"{language}_{gender}", EDGE_TTS_VOICES["hi_male"])
        
        communicate = edge_tts.Communicate(text, voice)
        await asyncio.wait_for(
            communicate.save(str(output_path)),
            timeout=8.0
        )
        
        return output_path.exists() and output_path.stat().st_size > 0
        
    except Exception as e:
        logger.error(f"❌ Edge TTS error: {e}")
        return False


# =============================================================================
# Text Preparation
# =============================================================================

def _prepare_text_fast(text: str, language: str) -> str:
    """Prepare and truncate text for fast TTS."""
    if not text:
        return ""
    
    # Remove markdown
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
    text = re.sub(r'_+([^_]+)_+', r'\1', text)
    text = re.sub(r'^[\s]*[-*•]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Aggressive truncation
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        # Find sentence break
        breaks = ['।', '.', '!', '?', ',']
        for b in breaks:
            pos = text.rfind(b)
            if pos > MAX_TEXT_LENGTH * 0.6:
                text = text[:pos + 1]
                break
        else:
            text = text.rstrip() + "..."
    
    return text


# =============================================================================
# Utilities
# =============================================================================

def generate_speech(text: str, language: str = "hi", gender: str = None) -> str:
    """Sync wrapper."""
    return asyncio.run(generate_speech_async(text, language, gender))


def get_tts_info() -> dict:
    return {"engine": "gTTS", "version": "4.2-ultrafast", "max_chars": MAX_TEXT_LENGTH, "cache": len(_audio_cache)}


def get_available_voices() -> dict:
    return {"hindi": {"male": "gTTS"}, "english": {"male": "gTTS"}}


def clear_cache():
    _audio_cache.clear()


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    import time as t
    
    async def test():
        print("=" * 50)
        print("TTS v4.2 ULTRA FAST Test")
        print(f"Max chars: {MAX_TEXT_LENGTH}")
        print("=" * 50)
        
        tests = [
            ("hi", "नमस्ते, यह परीक्षण है।"),
            ("hi", "भक्ति का मार्ग सहन करने का मार्ग है। हमें शांति रखनी चाहिए।"),
            ("en", "Welcome to Divya Vaani. This is a test."),
        ]
        
        for lang, text in tests:
            print(f"\n[{lang}] {text[:40]}...")
            start = t.time()
            url = await generate_speech_async(text, lang)
            elapsed = t.time() - start
            status = "✅" if elapsed < 3 else "⚠️"
            print(f"{status} {elapsed:.2f}s - {url}")
    
    asyncio.run(test())

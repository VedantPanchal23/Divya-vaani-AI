"""
Divya Vaani AI - TTS Engine v3.3 (Streamlined)
Supports:
1. Voice Cloning (XTTS) - Clone speaker's voice from reference audio
2. Edge TTS - Fast cloud TTS (default fallback)
3. gTTS - Google TTS (reliable fallback)
"""
import logging
import uuid
import asyncio
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Edge TTS voices (fast, reliable)
EDGE_TTS_VOICES = {
    "hi": "hi-IN-MadhurNeural",     # Good male Hindi voice
    "hi_female": "hi-IN-SwaraNeural",
    "en": "en-IN-PrabhatNeural",    # Indian English male
    "en_female": "en-IN-NeerjaNeural"
}

# Voice mode: "fast" (Edge TTS), "clone" (voice cloning), "gtts" (Google TTS)
DEFAULT_MODE = "fast"


# =============================================================================
# Main TTS Function (Smart Mode Selection)
# =============================================================================

async def generate_speech_async(text: str, language: str = "hi", mode: str = None) -> str:
    """
    Generate speech with intelligent mode selection.
    
    Args:
        text: Text to convert to speech
        language: "hi" for Hindi, "en" for English
        mode: "clone" (voice cloning), "fast" (Edge TTS), "gtts", or None (auto)
    
    Returns:
        URL path to audio file
    """
    if not text or not text.strip():
        return ""
    
    # Determine mode - check if voice cloning is enabled
    if mode is None:
        use_cloning = getattr(settings, 'USE_VOICE_CLONING', False)
        mode = "clone" if use_cloning else getattr(settings, 'TTS_MODE', DEFAULT_MODE)
    
    try:
        settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        
        audio_id = str(uuid.uuid4())[:8]
        filename = f"tts_{audio_id}.mp3"
        filepath = settings.AUDIO_DIR / filename
        
        # Try voice cloning first if enabled
        if mode == "clone":
            # For longer text, use chunked approach
            text_length = len(text.strip())
            if text_length > 500:
                logger.info(f"🎤 Long text ({text_length} chars), using chunked voice cloning...")
                result = await _generate_long_voice_cloning(text, language)
                if result:
                    return result
                logger.warning("Long voice cloning failed, trying single generation...")
            
            result = await _generate_with_voice_cloning(text, language, filepath)
            if result:
                return result
            logger.warning("⚠️ Voice cloning failed, falling back to Edge TTS (female voice)")
        
        # Try Edge TTS (fast mode) - THIS IS THE FALLBACK
        success = await _generate_with_edge_tts(text, language, filepath)
        if success:
            return f"/api/audio/{filename}"
        
        return ""
        
    except Exception as e:
        logger.error(f"❌ TTS failed: {e}")
        return ""


async def _generate_long_voice_cloning(text: str, language: str) -> Optional[str]:
    """Generate cloned speech for long text using chunking."""
    try:
        from core.voice_cloner import generate_long_cloned_speech, is_voice_cloning_available
        if is_voice_cloning_available():
            result = await generate_long_cloned_speech(text, language)
            if result:
                return result
    except Exception as e:
        logger.warning(f"Long voice cloning failed: {e}")
    return None


async def generate_long_speech_async(text: str, language: str = "hi") -> str:
    """Generate speech for longer text."""
    use_cloning = getattr(settings, 'USE_VOICE_CLONING', False)
    
    # For voice cloning with long text, use the chunked approach
    if use_cloning:
        try:
            from core.voice_cloner import generate_long_cloned_speech, is_voice_cloning_available
            if is_voice_cloning_available():
                result = await generate_long_cloned_speech(text, language)
                if result:
                    return result
        except Exception as e:
            logger.warning(f"Long voice cloning failed: {e}")
    
    # Fall back to regular generation (Edge TTS handles long text well)
    return await generate_speech_async(text, language, mode="fast")


# =============================================================================
# Voice Cloning (XTTS-v2)
# =============================================================================

async def _generate_with_voice_cloning(text: str, language: str, output_path: Path) -> Optional[str]:
    """
    Generate speech using voice cloning (XTTS-v2).
    Uses reference audio to clone the speaker's voice.
    """
    try:
        from core.voice_cloner import generate_cloned_speech, is_voice_cloning_available
        
        if not is_voice_cloning_available():
            logger.warning("Voice cloning not available (TTS library not installed)")
            return None
        
        logger.info(f"🎤 Voice cloning: generating speech ({len(text)} chars, {language})...")
        
        result = await generate_cloned_speech(
            text=text,
            language=language,
            output_path=output_path.with_suffix('.wav')  # XTTS outputs WAV
        )
        
        if result:
            logger.info(f"✅ Voice cloning successful: {result}")
        else:
            logger.warning(f"⚠️ Voice cloning returned None for text: '{text[:50]}...'")
        
        return result
        
    except ImportError:
        logger.warning("Voice cloner module not found")
        return None
    except Exception as e:
        logger.error(f"Voice cloning error: {e}")
        return None


# =============================================================================
# Edge TTS (Fast, Reliable)
# =============================================================================

async def _generate_with_edge_tts(text: str, language: str, output_path: Path) -> bool:
    """
    Generate speech using Microsoft Edge TTS.
    Very fast (~200-500ms), good quality, supports Hindi perfectly.
    Falls back to gTTS if Edge TTS fails (403 errors).
    """
    try:
        import edge_tts
        
        # Select voice based on language
        voice = EDGE_TTS_VOICES.get(language, EDGE_TTS_VOICES["hi"])
        
        # Clean text for TTS
        clean_text = _clean_text_for_tts(text)
        
        logger.info(f"🎤 Edge TTS: '{clean_text[:50]}...' with voice {voice}")
        
        # Generate with edge-tts
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(str(output_path))
        
        return output_path.exists()
        
    except ImportError:
        logger.error("❌ edge-tts not installed. Run: pip install edge-tts")
        return await _generate_with_gtts_fallback(text, language, output_path)
    except Exception as e:
        logger.error(f"❌ Edge TTS error: {e}")
        # Fallback to gTTS on any Edge TTS error (including 403)
        logger.info("🔄 Falling back to gTTS...")
        return await _generate_with_gtts_fallback(text, language, output_path)


async def _generate_with_gtts_fallback(text: str, language: str, output_path: Path) -> bool:
    """
    Fallback TTS using Google Text-to-Speech (gTTS).
    Slower than Edge TTS but more reliable.
    """
    try:
        from gtts import gTTS
        import asyncio
        
        clean_text = _clean_text_for_tts(text)
        
        # Map language codes
        gtts_lang = "hi" if language == "hi" else "en"
        
        logger.info(f"🎤 gTTS fallback: '{clean_text[:50]}...' with lang {gtts_lang}")
        
        # gTTS is synchronous, run in thread pool
        def generate_sync():
            tts = gTTS(text=clean_text, lang=gtts_lang, slow=False)
            tts.save(str(output_path))
            return output_path.exists()
        
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, generate_sync)
        
        if result:
            logger.info(f"✅ gTTS generated: {output_path.name}")
        return result
        
    except ImportError:
        logger.error("❌ gTTS not installed. Run: pip install gTTS")
        return False
    except Exception as e:
        logger.error(f"❌ gTTS fallback error: {e}")
        return False


def _clean_text_for_tts(text: str) -> str:
    """Clean and preprocess text for TTS."""
    if not text:
        return ""
    
    # Remove markdown formatting
    import re
    
    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    
    # Remove bold/italic markers
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
    text = re.sub(r'_+([^_]+)_+', r'\1', text)
    
    # Remove bullet points
    text = re.sub(r'^[\s]*[-*•]\s*', '', text, flags=re.MULTILINE)
    
    # Remove numbered lists
    text = re.sub(r'^[\s]*\d+\.\s*', '', text, flags=re.MULTILINE)
    
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Limit length (Edge TTS handles long text but there's a practical limit)
    max_chars = 5000
    if len(text) > max_chars:
        # Find a good breaking point
        text = text[:max_chars]
        last_period = text.rfind('।')
        if last_period == -1:
            last_period = text.rfind('.')
        if last_period > max_chars * 0.8:
            text = text[:last_period + 1]
    
    return text


# =============================================================================
# Sync Wrapper
# =============================================================================

def generate_speech(text: str, language: str = "hi") -> str:
    """Sync wrapper for generate_speech_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, generate_speech_async(text, language))
            return future.result()
    else:
        return loop.run_until_complete(generate_speech_async(text, language))


# =============================================================================
# API Info
# =============================================================================

def get_tts_info() -> dict:
    """Get TTS engine information."""
    return {
        "mode": getattr(settings, 'TTS_MODE', DEFAULT_MODE),
        "edge_tts_available": True,
        "voice_cloning_enabled": getattr(settings, 'USE_VOICE_CLONING', False),
        "voices": EDGE_TTS_VOICES
    }


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    async def test():
        print("Testing TTS Engine v3.0 (Optimized)")
        print("=" * 50)
        
        test_texts = [
            ("hi", "नमस्ते, मैं दिव्य वाणी AI हूँ।"),
            ("hi", "जीवन में सुख-दुख का आना-जाना लगा रहता है।"),
            ("en", "Welcome to Divya Vaani AI, your spiritual guide."),
        ]
        
        for lang, text in test_texts:
            print(f"\n[{lang}] Input: {text}")
            import time
            start = time.time()
            result = await generate_speech_async(text, lang)
            elapsed = time.time() - start
            print(f"Output: {result}")
            print(f"Time: {elapsed:.2f}s")
    
    asyncio.run(test())

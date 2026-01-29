"""
Divya Vaani AI - TTS Engine v3.0 (Optimized for Speed)
Uses Edge TTS as PRIMARY for fast response (supports Hindi/English)
Optional voice cloning with F5-TTS when quality > speed

Performance:
- Edge TTS: ~200-500ms latency (cloud, but fast)
- F5-TTS: ~10-60s latency (local, GPU needed for speed)
"""
import logging
import uuid
import asyncio
from pathlib import Path
from typing import Optional, Tuple

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

# Voice mode: "fast" (Edge TTS) or "clone" (F5-TTS)
DEFAULT_MODE = "fast"

# Global state
_voice_sample_path: Optional[Path] = None
_voice_sample_transcript: Optional[str] = None


# =============================================================================
# Main TTS Function (Fast Mode - Edge TTS)
# =============================================================================

async def generate_speech_async(text: str, language: str = "hi", mode: str = None) -> str:
    """
    Generate speech quickly using Edge TTS.
    
    Args:
        text: Text to convert to speech
        language: "hi" for Hindi, "en" for English
        mode: "fast" (Edge TTS) or "clone" (F5-TTS voice cloning)
    
    Returns:
        URL path to audio file
    """
    if not text or not text.strip():
        return ""
    
    mode = mode or getattr(settings, 'TTS_MODE', DEFAULT_MODE)
    
    try:
        settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        
        audio_id = str(uuid.uuid4())[:8]
        filename = f"tts_{audio_id}.mp3"
        filepath = settings.AUDIO_DIR / filename
        
        if mode == "clone":
            # Try voice cloning (slower but more authentic)
            voice_sample, transcript = _find_voice_sample()
            if voice_sample:
                success = await _generate_with_f5tts(text, voice_sample, transcript, filepath)
                if success:
                    logger.info(f"🎤 Voice clone generated: {filename}")
                    return f"/api/audio/{filename}"
            logger.warning("Voice sample not found, falling back to Edge TTS")
        
        # Fast mode: Edge TTS (default)
        success = await _generate_with_edge_tts(text, language, filepath)
        if success:
            logger.info(f"🎤 Edge TTS generated: {filename}")
            return f"/api/audio/{filename}"
        
        return ""
        
    except Exception as e:
        logger.error(f"❌ TTS failed: {e}")
        return ""


async def generate_long_speech_async(text: str, language: str = "hi") -> str:
    """Generate speech for longer text - Edge TTS handles this well."""
    return await generate_speech_async(text, language)


# =============================================================================
# Edge TTS (Fast, Reliable)
# =============================================================================

async def _generate_with_edge_tts(text: str, language: str, output_path: Path) -> bool:
    """
    Generate speech using Microsoft Edge TTS.
    Very fast (~200-500ms), good quality, supports Hindi perfectly.
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
        return False
    except Exception as e:
        logger.error(f"❌ Edge TTS error: {e}")
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
# F5-TTS Voice Cloning (Optional, Slower)
# =============================================================================

def _find_voice_sample() -> Tuple[Optional[Path], Optional[str]]:
    """Find Maharaj's voice sample for cloning."""
    global _voice_sample_path, _voice_sample_transcript
    
    if _voice_sample_path is not None:
        return _voice_sample_path, _voice_sample_transcript
    
    # Default transcript for reference
    default_transcript = "प्रेमानंद महाराज का प्रवचन। भगवद्गीता के अनुसार कर्म और धर्म का मार्ग।"
    
    # Check configured path
    if settings.VOICE_SAMPLE_PATH and Path(settings.VOICE_SAMPLE_PATH).exists():
        _voice_sample_path = Path(settings.VOICE_SAMPLE_PATH)
        transcript_path = _voice_sample_path.with_suffix('.txt')
        _voice_sample_transcript = transcript_path.read_text(encoding='utf-8').strip() if transcript_path.exists() else default_transcript
        return _voice_sample_path, _voice_sample_transcript
    
    # Check reference_audio directory
    ref_dir = Path(__file__).parent.parent / "data" / "reference_audio"
    if ref_dir.exists():
        for audio_file in ref_dir.glob("*.wav"):
            transcript_path = audio_file.with_suffix('.txt')
            if transcript_path.exists():
                _voice_sample_path = audio_file
                _voice_sample_transcript = transcript_path.read_text(encoding='utf-8').strip()
                return _voice_sample_path, _voice_sample_transcript
    
    # Check Input folder
    input_dir = Path(__file__).parent.parent.parent / "Input"
    for name in ["maharaj_audio.mp3", "maharaj-voice.mp3", "maharaj_voice.wav"]:
        path = input_dir / name
        if path.exists():
            _voice_sample_path = path
            _voice_sample_transcript = default_transcript
            return _voice_sample_path, _voice_sample_transcript
    
    return None, None


async def _generate_with_f5tts(
    text: str, 
    voice_sample: Path,
    ref_transcript: str, 
    output_path: Path
) -> bool:
    """Generate speech using F5-TTS with voice cloning (slower but authentic)."""
    try:
        import sys
        python_exe = sys.executable
        
        # Clean text
        clean_text = _clean_text_for_tts(text)
        if len(clean_text) > 200:
            clean_text = clean_text[:200]
            last_punct = max(clean_text.rfind('।'), clean_text.rfind('.'), clean_text.rfind(','))
            if last_punct > 150:
                clean_text = clean_text[:last_punct + 1]
        
        # F5-TTS CLI
        wav_output = output_path.with_suffix('.wav')
        cmd = [
            python_exe, "-m", "f5_tts.infer.infer_cli",
            "-r", str(voice_sample.absolute()),
            "-s", ref_transcript,
            "-t", clean_text,
            "-o", str(wav_output.parent),
            "-n", wav_output.stem,
            "--speed", "1.0",
        ]
        
        logger.info(f"🎤 F5-TTS voice cloning: '{clean_text[:30]}...'")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            await asyncio.wait_for(process.communicate(), timeout=120)
        except asyncio.TimeoutError:
            logger.warning("⚠️ F5-TTS timeout, process may still be running")
            return False
        
        # Check for output
        if wav_output.exists():
            # Convert to mp3 for smaller file size
            await _convert_to_mp3(wav_output, output_path)
            return output_path.exists()
        
        return False
        
    except FileNotFoundError:
        logger.warning("F5-TTS not installed, using Edge TTS")
        return False
    except Exception as e:
        logger.error(f"❌ F5-TTS error: {e}")
        return False


async def _convert_to_mp3(wav_path: Path, mp3_path: Path) -> bool:
    """Convert WAV to MP3 using ffmpeg."""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-b:a", "128k",
            str(mp3_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.wait_for(process.communicate(), timeout=30)
        
        # Clean up wav
        if mp3_path.exists() and wav_path.exists():
            wav_path.unlink()
        
        return mp3_path.exists()
        
    except Exception:
        # If conversion fails, just rename
        if wav_path.exists():
            wav_path.rename(mp3_path)
        return mp3_path.exists()


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
    voice_sample, _ = _find_voice_sample()
    return {
        "mode": getattr(settings, 'TTS_MODE', DEFAULT_MODE),
        "edge_tts_available": True,  # Always available via pip
        "voice_cloning_available": voice_sample is not None,
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

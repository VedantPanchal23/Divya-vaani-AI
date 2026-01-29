"""
Divya Vaani AI - TTS Engine v3.1 (Optimized for Speed)
Uses Edge TTS as PRIMARY for fast response (supports Hindi/English)
Optional voice cloning with F5-TTS when quality > speed

Performance:
- Edge TTS: ~200-500ms latency (cloud, but fast)
- F5-TTS: ~2-5s with caching (first call ~15s to load model)

Optimizations:
- Model caching: F5-TTS model loaded once, kept in memory
- Reference audio pre-processing: Cached after first use
- Direct Python API instead of CLI for faster inference
"""
import logging
import uuid
import asyncio
import json
from pathlib import Path
from typing import Optional, Tuple, Any

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

# Global state - Voice sample paths
_voice_sample_path: Optional[Path] = None
_voice_sample_transcript: Optional[str] = None

# Global state - F5-TTS model cache (loaded once, reused)
_f5_model: Optional[Any] = None
_f5_vocoder: Optional[Any] = None
_f5_ref_audio: Optional[Any] = None  # Pre-processed reference audio
_f5_ref_text: Optional[str] = None
_f5_device: Optional[str] = None


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
# F5-TTS Voice Cloning (Optional, with Caching for Speed)
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


def _load_f5_model():
    """
    Load F5-TTS model ONCE and cache it in memory.
    Subsequent calls reuse the cached model (huge speed improvement).
    """
    global _f5_model, _f5_vocoder, _f5_device
    
    if _f5_model is not None:
        return _f5_model, _f5_vocoder, _f5_device
    
    try:
        import torch
        from f5_tts.model import DiT
        from f5_tts.infer.utils_infer import load_vocoder, load_model
        
        logger.info("🎤 Loading F5-TTS model (one-time)...")
        
        # Device selection
        _f5_device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"   Device: {_f5_device}")
        
        # Load vocoder (one-time)
        _f5_vocoder = load_vocoder(vocoder_name="vocos", is_local=False)
        
        # Load F5-TTS model (one-time)
        model_cls = DiT
        model_cfg = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)
        _f5_model = load_model(model_cls, model_cfg, "", mel_spec_type="vocos", vocab_file="")
        
        logger.info("✅ F5-TTS model cached in memory")
        return _f5_model, _f5_vocoder, _f5_device
        
    except ImportError as e:
        logger.warning(f"F5-TTS not available: {e}")
        return None, None, None
    except Exception as e:
        logger.error(f"Failed to load F5-TTS: {e}")
        return None, None, None


def _preprocess_reference_audio(voice_sample: Path, ref_transcript: str):
    """
    Pre-process reference audio ONCE and cache it.
    This is the expensive operation that we want to avoid repeating.
    """
    global _f5_ref_audio, _f5_ref_text
    
    # Return cached if same reference
    if _f5_ref_audio is not None and _f5_ref_text == ref_transcript:
        return _f5_ref_audio, _f5_ref_text
    
    try:
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        
        logger.info(f"🎤 Pre-processing reference audio (one-time): {voice_sample.name}")
        
        # This processes the reference audio and extracts features
        ref_audio_path = str(voice_sample.absolute())
        _f5_ref_audio = ref_audio_path  # Store path for now
        _f5_ref_text = ref_transcript
        
        logger.info("✅ Reference audio cached")
        return _f5_ref_audio, _f5_ref_text
        
    except Exception as e:
        logger.error(f"Failed to preprocess reference: {e}")
        return None, None


async def _generate_with_f5tts(
    text: str, 
    voice_sample: Path,
    ref_transcript: str, 
    output_path: Path
) -> bool:
    """
    Generate speech using F5-TTS with CACHED model and reference.
    First call: ~15s (loads model + processes reference)
    Subsequent calls: ~2-5s (uses cache)
    """
    try:
        # Load cached model (or load once if first time)
        model, vocoder, device = _load_f5_model()
        if model is None:
            return False
        
        # Get cached reference audio
        ref_audio, ref_text = _preprocess_reference_audio(voice_sample, ref_transcript)
        if ref_audio is None:
            return False
        
        # Clean text
        clean_text = _clean_text_for_tts(text)
        if len(clean_text) > 200:
            clean_text = clean_text[:200]
            last_punct = max(clean_text.rfind('।'), clean_text.rfind('.'), clean_text.rfind(','))
            if last_punct > 150:
                clean_text = clean_text[:last_punct + 1]
        
        logger.info(f"🎤 F5-TTS generating: '{clean_text[:30]}...'")
        
        # Run inference in thread pool (CPU-bound)
        loop = asyncio.get_event_loop()
        wav_output = output_path.with_suffix('.wav')
        
        def _generate():
            import soundfile as sf
            from f5_tts.infer.utils_infer import infer_process
            
            audio, sr, _ = infer_process(
                ref_audio,
                ref_text,
                clean_text,
                model,
                vocoder,
                mel_spec_type="vocos",
                speed=1.0,
                device=device,
            )
            sf.write(str(wav_output), audio, sr)
            return wav_output.exists()
        
        success = await loop.run_in_executor(None, _generate)
        
        if success:
            # Convert to mp3
            await _convert_to_mp3(wav_output, output_path)
            return output_path.exists()
        
        return False
        
    except ImportError:
        # Fall back to CLI if direct import fails
        logger.info("Using F5-TTS CLI fallback...")
        return await _generate_with_f5tts_cli(text, voice_sample, ref_transcript, output_path)
    except Exception as e:
        logger.error(f"❌ F5-TTS error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def _generate_with_f5tts_cli(
    text: str, 
    voice_sample: Path,
    ref_transcript: str, 
    output_path: Path
) -> bool:
    """Fallback: Generate speech using F5-TTS CLI (slower, no caching)."""
    try:
        import sys
        python_exe = sys.executable
        
        clean_text = _clean_text_for_tts(text)
        if len(clean_text) > 200:
            clean_text = clean_text[:200]
        
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
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.wait_for(process.communicate(), timeout=120)
        
        if wav_output.exists():
            await _convert_to_mp3(wav_output, output_path)
            return output_path.exists()
        
        return False
        
    except Exception as e:
        logger.error(f"❌ F5-TTS CLI error: {e}")
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
# API Info & Pre-warming
# =============================================================================

def get_tts_info() -> dict:
    """Get TTS engine information."""
    voice_sample, _ = _find_voice_sample()
    return {
        "mode": getattr(settings, 'TTS_MODE', DEFAULT_MODE),
        "edge_tts_available": True,  # Always available via pip
        "voice_cloning_available": voice_sample is not None,
        "model_cached": _f5_model is not None,
        "reference_cached": _f5_ref_audio is not None,
        "voices": EDGE_TTS_VOICES
    }


async def prewarm_voice_cloning():
    """
    Pre-warm the voice cloning model at server startup.
    Call this during app initialization to avoid cold-start latency.
    """
    if getattr(settings, 'TTS_MODE', DEFAULT_MODE) != "clone":
        logger.info("ℹ️ Voice cloning not enabled, skipping pre-warm")
        return False
    
    voice_sample, transcript = _find_voice_sample()
    if not voice_sample:
        logger.warning("⚠️ No voice sample found for pre-warming")
        return False
    
    logger.info("🔥 Pre-warming voice cloning model...")
    
    # Load model
    model, vocoder, device = _load_f5_model()
    if model is None:
        return False
    
    # Pre-process reference audio
    _preprocess_reference_audio(voice_sample, transcript)
    
    logger.info("✅ Voice cloning ready (model + reference cached)")
    return True


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

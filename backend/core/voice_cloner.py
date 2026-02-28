"""
Divya Vaani AI - Voice Cloning Engine
Uses Coqui XTTS-v2 for high-quality voice cloning in Hindi/English.

Features:
- Clone voice from the dedicated reference audio (maharaj_audio.mp3)
- Supports Hindi and English
- Caches model for fast subsequent generations
- Falls back to gTTS if cloning fails

IMPORTANT: Voice cloning uses ONLY the designated reference audio file.
User uploaded files are transcribed, but voice is cloned from reference.
"""
import logging
import asyncio
import uuid
import os
from pathlib import Path
from typing import Optional, List, Tuple
import tempfile

from config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Reference Audio Configuration
# =============================================================================

# The designated file for voice cloning (or any WAV from kaggle_upload)
REFERENCE_AUDIO_FILENAME = "maharaj_audio.mp3"

# Global state for model caching
_xtts_model = None
_xtts_config = None
_reference_audio_cache = {}  # Cache processed reference audio
_cached_reference_path = None  # Cached path to prepared reference
_cached_speaker_embedding = None  # Cached speaker embedding for FAST inference
_cached_gpt_cond_latent = None  # Cached GPT conditioning latent


def clear_voice_cloning_cache():
    """Clear all cached data to force regeneration."""
    global _xtts_model, _xtts_config, _reference_audio_cache, _cached_reference_path
    global _cached_speaker_embedding, _cached_gpt_cond_latent
    
    logger.info("🔄 Clearing voice cloning cache...")
    
    # Clear cached reference audio file
    if _cached_reference_path and Path(_cached_reference_path).exists():
        try:
            Path(_cached_reference_path).unlink()
            logger.info("   Deleted cached reference audio")
        except Exception as e:
            logger.debug(f"Could not delete cached reference: {e}")
    
    _cached_reference_path = None
    _reference_audio_cache = {}
    _cached_speaker_embedding = None
    _cached_gpt_cond_latent = None
    # Don't clear model - it's expensive to reload
    
    logger.info("✅ Voice cloning cache cleared")


def get_reference_audio_path() -> Optional[Path]:
    """
    Get the path to the reference audio file for voice cloning.
    Searches multiple locations including kaggle_upload WAV files.
    """
    # Check multiple possible locations
    possible_paths = [
        # Primary: Input folder
        Path(__file__).parent.parent.parent / "Input" / REFERENCE_AUDIO_FILENAME,
        # Secondary: reference_audio folder
        Path(__file__).parent.parent / "data" / "reference_audio" / REFERENCE_AUDIO_FILENAME,
        # Tertiary: Check config path
        Path(settings.REFERENCE_AUDIO_PATH) if settings.REFERENCE_AUDIO_PATH else None,
    ]
    
    for path in possible_paths:
        if path and path.exists():
            logger.info(f"🎤 Using reference audio: {path}")
            return path
    
    # Fallback: Use a WAV file from kaggle_upload (Maharaj Ji's voice samples)
    kaggle_dir = Path(__file__).parent.parent.parent / "kaggle_upload"
    if kaggle_dir.exists():
        wav_files = sorted(kaggle_dir.glob("*.wav"))
        if wav_files:
            # Pick the largest file (likely the cleanest/longest sample)
            best_file = max(wav_files, key=lambda f: f.stat().st_size)
            logger.info(f"🎤 Using kaggle_upload reference audio: {best_file.name} ({best_file.stat().st_size / 1024:.0f}KB)")
            return best_file
    
    # Also check reference_audio for any WAV/MP3 files
    ref_dir = Path(__file__).parent.parent / "data" / "reference_audio"
    if ref_dir.exists():
        for ext in ["*.wav", "*.mp3", "*.flac"]:
            files = list(ref_dir.glob(ext))
            if files:
                logger.info(f"🎤 Using reference audio: {files[0]}")
                return files[0]
    
    logger.warning(f"⚠️ Reference audio not found: {REFERENCE_AUDIO_FILENAME}")
    logger.warning(f"   Place audio in: Input/{REFERENCE_AUDIO_FILENAME} or kaggle_upload/")
    return None


def _prepare_reference_audio(audio_path: Path, target_duration: float = 60.0) -> Optional[Path]:
    """
    Prepare reference audio for voice cloning.
    - Converts to WAV if needed
    - Uses optimal length (30-60 seconds for best voice capture)
    - Takes from START of audio (usually cleaner speech)
    - Ensures correct sample rate for XTTS
    
    IMPORTANT: Longer reference = better voice capture for XTTS-v2
    """
    try:
        from pydub import AudioSegment
        from pydub.effects import normalize
        
        logger.info(f"🎤 Loading reference audio: {audio_path}")
        
        # Load audio
        audio = AudioSegment.from_file(str(audio_path))
        original_duration = len(audio) / 1000  # seconds
        logger.info(f"   Original duration: {original_duration:.1f}s")
        
        # Use first N seconds (start usually has cleaner speech)
        target_duration_ms = int(target_duration * 1000)
        if len(audio) > target_duration_ms:
            audio = audio[:target_duration_ms]
            logger.info(f"   Trimmed to: {target_duration}s (from start)")
        
        # Convert to mono
        audio = audio.set_channels(1)
        
        # Set sample rate to 22050 Hz (XTTS requirement)
        audio = audio.set_frame_rate(22050)
        
        # Normalize audio for consistent volume
        audio = normalize(audio)
        
        # Export as 16-bit WAV (XTTS requirement)
        temp_path = Path(tempfile.gettempdir()) / f"ref_audio_xtts.wav"
        audio.export(
            str(temp_path), 
            format="wav",
            parameters=["-acodec", "pcm_s16le"]  # 16-bit PCM
        )
        
        logger.info(f"   ✅ Reference audio prepared: {temp_path}")
        return temp_path
        
    except Exception as e:
        logger.error(f"Failed to prepare reference audio: {e}")
        import traceback
        traceback.print_exc()
        return None


def _load_xtts_model():
    """
    Load XTTS-v2 model with caching.
    First load takes ~30-60 seconds, subsequent calls are instant.
    """
    global _xtts_model, _xtts_config
    
    if _xtts_model is not None:
        return _xtts_model, _xtts_config
    
    try:
        import torch
        
        # Fix for PyTorch 2.6+ weights_only issue
        # Monkey-patch the TTS library's load_fsspec function to use weights_only=False
        # This is safe since we trust the Coqui TTS model files
        import TTS.utils.io
        _original_load_fsspec = TTS.utils.io.load_fsspec
        
        def _patched_load_fsspec(path, map_location=None, **kwargs):
            # Force weights_only=False for TTS model loading
            kwargs['weights_only'] = False
            return _original_load_fsspec(path, map_location=map_location, **kwargs)
        
        TTS.utils.io.load_fsspec = _patched_load_fsspec
        
        from TTS.api import TTS
        
        logger.info("🎤 Loading XTTS-v2 model (first time only, may take a minute)...")
        
        # Determine device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"   Device: {device}")
        
        # Use the simpler TTS API which handles model loading automatically
        _xtts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        _xtts_config = {"device": device}  # Store config info
        
        logger.info("✅ XTTS-v2 model loaded and cached!")
        return _xtts_model, _xtts_config
        
    except ImportError as e:
        logger.error(f"❌ TTS library not installed: {e}")
        logger.error("   Install with: pip install TTS")
        return None, None
    except Exception as e:
        logger.error(f"❌ Failed to load XTTS model: {e}")
        import traceback
        traceback.print_exc()
        return None, None


async def generate_cloned_speech(
    text: str,
    language: str = "hi",
    reference_audio: Optional[Path] = None,
    output_path: Optional[Path] = None
) -> Optional[str]:
    """
    Generate speech using voice cloning from the designated reference audio.
    
    IMPORTANT: Always uses maharaj_audio.mp3 as reference, regardless of 
    what audio the user uploads. User uploads are for transcription only.
    
    OPTIMIZED: Uses cached speaker embeddings for 3-5x faster inference after
    first generation. First call: ~10-15s, subsequent calls: ~2-5s.
    
    Args:
        text: Text to synthesize
        language: "hi" for Hindi, "en" for English
        reference_audio: Ignored - always uses designated reference
        output_path: Output file path (auto-generated if None)
    
    Returns:
        URL path to generated audio file, or None if failed
    """
    global _cached_reference_path, _cached_speaker_embedding, _cached_gpt_cond_latent
    
    if not text or not text.strip():
        return None
    
    # Ensure output directory exists
    settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate output path if not provided
    if output_path is None:
        audio_id = str(uuid.uuid4())[:8]
        output_path = settings.AUDIO_DIR / f"clone_{audio_id}.wav"
    
    # ALWAYS use the designated reference audio (maharaj_audio.mp3)
    reference_audio = get_reference_audio_path()
    if reference_audio is None:
        logger.error(f"❌ Reference audio not found: {REFERENCE_AUDIO_FILENAME}")
        logger.error(f"   Please ensure the file exists in: Input/{REFERENCE_AUDIO_FILENAME}")
        return None
    
    try:
        # Load model (cached after first call)
        tts_model, config = _load_xtts_model()
        if tts_model is None:
            return None
        
        # Prepare reference audio (cached after first preparation)
        if _cached_reference_path is None or not Path(_cached_reference_path).exists():
            logger.info(f"🎤 Preparing reference audio: {reference_audio.name}")
            prepared_ref = _prepare_reference_audio(reference_audio)
            if prepared_ref:
                _cached_reference_path = prepared_ref
                logger.info(f"✅ Reference audio prepared and cached")
        
        if _cached_reference_path is None:
            logger.error("Failed to prepare reference audio")
            return None
        
        # Clean text based on language
        clean_text = _clean_text_for_cloning(text, language)
        
        if not clean_text or len(clean_text.strip()) < 2:
            logger.error("Text too short after cleaning")
            return None
        
        # Map language codes - XTTS uses full language names
        # Detect language from text if not specified
        detected_lang = _detect_language(clean_text)
        xtts_lang = detected_lang if detected_lang else ("hi" if language == "hi" else "en")
        
        logger.info(f"🎤 Cloning voice: '{clean_text[:50]}...' in {xtts_lang}")
        logger.info(f"   Text length: {len(clean_text)} chars")
        
        # Run inference in thread pool with CACHED speaker embeddings
        loop = asyncio.get_running_loop()
        
        def _generate_with_cached_embeddings():
            """
            OPTIMIZED: Use cached speaker embeddings for faster inference.
            First call computes and caches embeddings, subsequent calls reuse them.
            """
            global _cached_speaker_embedding, _cached_gpt_cond_latent
            
            try:
                # Access the underlying XTTS model
                synthesizer = tts_model.synthesizer
                xtts = synthesizer.tts_model
                
                # Compute and cache speaker embeddings (expensive, do once)
                if _cached_gpt_cond_latent is None or _cached_speaker_embedding is None:
                    logger.info("   Computing speaker embeddings (one-time)...")
                    _cached_gpt_cond_latent, _cached_speaker_embedding = xtts.get_conditioning_latents(
                        audio_path=[str(_cached_reference_path)],
                        gpt_cond_len=30,  # Use more audio for better voice capture
                        gpt_cond_chunk_len=4,
                        max_ref_length=60  # Use up to 60s of reference
                    )
                    logger.info("   ✅ Speaker embeddings cached!")
                
                # Generate speech using cached embeddings (FAST!)
                # Using LOW temperature for CONSISTENT voice across all generations
                out = xtts.inference(
                    text=clean_text,
                    language=xtts_lang,
                    gpt_cond_latent=_cached_gpt_cond_latent,
                    speaker_embedding=_cached_speaker_embedding,
                    temperature=0.1,  # VERY LOW for consistent voice (was 0.65)
                    length_penalty=1.0,
                    repetition_penalty=5.0,  # Higher to prevent repetition
                    top_k=30,  # Lower for more deterministic output
                    top_p=0.7,  # Lower for consistency
                    enable_text_splitting=True
                )
                
                # Save the audio
                import torchaudio
                torchaudio.save(str(output_path), out["wav"].unsqueeze(0).cpu(), 24000)
                return output_path.exists()
                
            except Exception as e:
                logger.warning(f"Optimized inference failed, using fallback: {e}")
                # Fallback to standard method
                tts_model.tts_to_file(
                    text=clean_text,
                    speaker_wav=str(_cached_reference_path),
                    language=xtts_lang,
                    file_path=str(output_path),
                    split_sentences=True
                )
                return output_path.exists()
        
        success = await loop.run_in_executor(None, _generate_with_cached_embeddings)
        
        if success:
            logger.info(f"✅ Voice cloning complete: {output_path.name}")
            
            # Convert to MP3 for smaller file size
            mp3_path = output_path.with_suffix('.mp3')
            await _convert_wav_to_mp3(output_path, mp3_path)
            
            return f"/api/audio/{mp3_path.name}"
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Voice cloning failed: {e}")
        import traceback
        traceback.print_exc()
        return None


async def _convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> bool:
    """Convert WAV to MP3 for smaller file size."""
    try:
        from pydub import AudioSegment
        
        loop = asyncio.get_running_loop()
        
        def convert():
            audio = AudioSegment.from_wav(str(wav_path))
            audio.export(str(mp3_path), format="mp3", bitrate="128k")
            # Remove original WAV
            wav_path.unlink()
            return mp3_path.exists()
        
        return await loop.run_in_executor(None, convert)
    except Exception as e:
        logger.error(f"Failed to convert to MP3: {e}")
        return False


def _clean_text_for_cloning(text: str, language: str = "hi") -> str:
    """
    Clean text for voice cloning TTS.
    Preserves Hindi/Devanagari characters properly.
    """
    import re
    
    if not text:
        return ""
    
    # Remove markdown formatting
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
    text = re.sub(r'_+([^_]+)_+', r'\1', text)
    text = re.sub(r'^[\s]*[-*•]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'https?://\S+', '', text)
    
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    
    # Normalize whitespace (preserve Hindi characters)
    text = re.sub(r'[ \t]+', ' ', text)  # Only horizontal whitespace
    text = re.sub(r'\n+', ' ', text)  # Newlines to space
    text = text.strip()
    
    # XTTS works best with moderate length (not too short, not too long)
    max_chars = 800  # Increased for better context
    if len(text) > max_chars:
        text = text[:max_chars]
        # Find good breaking point based on language
        if language == "hi":
            # Hindi punctuation: । (danda), | (pipe used as danda)
            for punct in ['।', '|', '.', '!', '?', ',']:
                last_punct = text.rfind(punct)
                if last_punct > max_chars * 0.6:
                    text = text[:last_punct + 1]
                    break
        else:
            for punct in ['.', '!', '?', ',', ';']:
                last_punct = text.rfind(punct)
                if last_punct > max_chars * 0.6:
                    text = text[:last_punct + 1]
                    break
    
    return text


def _detect_language(text: str) -> str:
    """
    Detect if text is primarily Hindi or English.
    Returns 'hi' for Hindi/Devanagari, 'en' for English/Latin.
    """
    import re
    
    if not text:
        return "en"
    
    # Count Devanagari characters (Hindi)
    devanagari_pattern = re.compile(r'[\u0900-\u097F]')
    devanagari_count = len(devanagari_pattern.findall(text))
    
    # Count Latin characters (English)
    latin_pattern = re.compile(r'[a-zA-Z]')
    latin_count = len(latin_pattern.findall(text))
    
    total = devanagari_count + latin_count
    if total == 0:
        return "en"
    
    # If more than 30% Devanagari, treat as Hindi
    if devanagari_count / total > 0.3:
        return "hi"
    
    return "en"


async def generate_long_cloned_speech(
    text: str,
    language: str = "hi",
    reference_audio: Optional[Path] = None,
    output_path: Optional[Path] = None
) -> Optional[str]:
    """
    Generate speech for longer text by chunking and combining.
    
    For text longer than 500 characters, splits into chunks,
    generates each separately, and combines into one audio file.
    """
    if not text or not text.strip():
        return None
    
    # For short text, use single generation
    if len(text) <= 500:
        return await generate_cloned_speech(text, language, reference_audio, output_path)
    
    # Split into sentences/chunks
    chunks = _split_text_into_chunks(text, max_chars=400)
    
    if not chunks:
        logger.warning("No chunks generated from text")
        return None
    
    logger.info(f"🎤 Long text ({len(text)} chars) split into {len(chunks)} chunks")
    
    # Generate audio for each chunk
    chunk_paths = []
    try:
        for i, chunk in enumerate(chunks):
            logger.info(f"   Generating chunk {i+1}/{len(chunks)}...")
            chunk_id = str(uuid.uuid4())[:8]
            chunk_path = settings.AUDIO_DIR / f"chunk_{chunk_id}.wav"
            
            result = await generate_cloned_speech(chunk, language, reference_audio, chunk_path)
            if result:
                # The result is a URL like /api/audio/clone_xxx.mp3
                # Extract the filename and get the actual path
                filename = result.split('/')[-1]
                actual_path = settings.AUDIO_DIR / filename
                if actual_path.exists():
                    chunk_paths.append(actual_path)
                    logger.info(f"   ✅ Chunk {i+1} saved: {filename}")
                else:
                    logger.warning(f"   ⚠️ Chunk {i+1} file not found: {actual_path}")
            else:
                logger.warning(f"   ⚠️ Chunk {i+1} generation failed")
        
        if not chunk_paths:
            logger.error("No chunks were successfully generated")
            return None
        
        logger.info(f"🎤 Combining {len(chunk_paths)} audio chunks...")
        
        # Combine all chunks
        combined_path = await _combine_audio_chunks(chunk_paths, output_path)
        
        # Cleanup chunk files
        for p in chunk_paths:
            try:
                p.unlink()
            except Exception as e:
                logger.debug(f"Could not delete chunk file: {e}")
        
        if combined_path:
            logger.info(f"✅ Long speech generation complete: {combined_path}")
        
        return combined_path
        
    except Exception as e:
        logger.error(f"Long speech generation failed: {e}")
        import traceback
        traceback.print_exc()
        # Cleanup on error
        for p in chunk_paths:
            try:
                p.unlink()
            except Exception as e:
                logger.debug(f"Could not cleanup chunk: {e}")
        return None


def _split_text_into_chunks(text: str, max_chars: int = 400) -> List[str]:
    """Split text into chunks at sentence boundaries."""
    import re
    
    # Split by sentence-ending punctuation
    sentences = re.split(r'([।.!?]+)', text)
    
    chunks = []
    current_chunk = ""
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ""
        full_sentence = sentence + punct
        
        if len(current_chunk) + len(full_sentence) <= max_chars:
            current_chunk += full_sentence
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = full_sentence
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks


async def _combine_audio_chunks(chunk_paths: List[Path], output_path: Optional[Path] = None) -> Optional[str]:
    """Combine multiple audio files into one."""
    try:
        from pydub import AudioSegment
        
        if not chunk_paths:
            return None
        
        loop = asyncio.get_running_loop()
        
        if output_path is None:
            audio_id = str(uuid.uuid4())[:8]
            output_path = settings.AUDIO_DIR / f"combined_{audio_id}.mp3"
        
        def combine():
            combined = AudioSegment.empty()
            
            for path in chunk_paths:
                if path.suffix == '.mp3':
                    audio = AudioSegment.from_mp3(str(path))
                else:
                    audio = AudioSegment.from_wav(str(path))
                combined += audio
            
            combined.export(str(output_path), format="mp3", bitrate="128k")
            return output_path.exists()
        
        success = await loop.run_in_executor(None, combine)
        
        if success:
            return f"/api/audio/{output_path.name}"
        return None
        
    except Exception as e:
        logger.error(f"Failed to combine audio chunks: {e}")
        return None


def is_voice_cloning_available() -> bool:
    """Check if voice cloning is available (TTS library installed)."""
    try:
        import TTS
        return True
    except ImportError:
        return False


def get_voice_cloning_status() -> dict:
    """Get status of voice cloning system."""
    ref_path = get_reference_audio_path()
    return {
        "available": is_voice_cloning_available(),
        "model_loaded": _xtts_model is not None,
        "reference_audio_found": ref_path is not None,
        "reference_audio_file": REFERENCE_AUDIO_FILENAME,
        "reference_audio_path": str(ref_path) if ref_path else None,
        "reference_prepared": _cached_reference_path is not None,
        "embeddings_cached": _cached_speaker_embedding is not None,
        "ready_for_fast_inference": _cached_speaker_embedding is not None and _cached_gpt_cond_latent is not None
    }


async def prewarm_voice_cloning():
    """
    Pre-warm the voice cloning model and compute speaker embeddings at startup.
    This eliminates cold-start latency - first TTS request will be fast!
    
    Call this during app initialization:
        asyncio.create_task(prewarm_voice_cloning())
    """
    global _cached_reference_path, _cached_speaker_embedding, _cached_gpt_cond_latent
    
    logger.info("🔥 Pre-warming voice cloning system...")
    
    if not is_voice_cloning_available():
        logger.warning("⚠️ TTS library not installed, skipping pre-warm")
        return False
    
    # Get reference audio
    reference_audio = get_reference_audio_path()
    if reference_audio is None:
        logger.warning(f"⚠️ Reference audio not found: {REFERENCE_AUDIO_FILENAME}")
        return False
    
    try:
        # Load model
        logger.info("   Loading XTTS model...")
        tts_model, config = _load_xtts_model()
        if tts_model is None:
            return False
        
        # Prepare reference audio
        logger.info("   Preparing reference audio...")
        if _cached_reference_path is None:
            prepared_ref = _prepare_reference_audio(reference_audio)
            if prepared_ref:
                _cached_reference_path = prepared_ref
        
        if _cached_reference_path is None:
            return False
        
        # Compute and cache speaker embeddings
        logger.info("   Computing speaker embeddings...")
        loop = asyncio.get_running_loop()
        
        def _compute_embeddings():
            global _cached_gpt_cond_latent, _cached_speaker_embedding
            
            synthesizer = tts_model.synthesizer
            xtts = synthesizer.tts_model
            
            _cached_gpt_cond_latent, _cached_speaker_embedding = xtts.get_conditioning_latents(
                audio_path=[str(_cached_reference_path)],
                gpt_cond_len=30,
                gpt_cond_chunk_len=4,
                max_ref_length=60
            )
            return True
        
        await loop.run_in_executor(None, _compute_embeddings)
        
        logger.info("✅ Voice cloning pre-warmed and ready!")
        logger.info("   - Model: XTTS-v2 loaded")
        logger.info("   - Reference: maharaj_audio.mp3 processed")
        logger.info("   - Embeddings: Cached for fast inference")
        return True
        
    except Exception as e:
        logger.error(f"❌ Pre-warming failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_reference_audio_files() -> List[Path]:
    """
    Get the designated reference audio file.
    Returns list for API compatibility, but only contains the one designated file.
    """
    ref_path = get_reference_audio_path()
    return [ref_path] if ref_path else []


def get_reference_audio_dir() -> Path:
    """Get the directory containing the reference audio file."""
    ref_path = get_reference_audio_path()
    if ref_path:
        return ref_path.parent
    return Path(__file__).parent.parent / "data" / "reference_audio"

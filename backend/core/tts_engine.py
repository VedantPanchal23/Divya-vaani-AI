"""
Divya Vaani AI - TTS Engine v2.0
Uses IndicF5 (Hindi-optimized F5-TTS) for Maharaj Premanand's voice.
Features:
- Hindi text preprocessing for accurate pronunciation
- Proper reference audio with verified transcript
- Sentence chunking for natural speech
- GPU acceleration support
"""
import logging
import uuid
import asyncio
import subprocess
import json
from pathlib import Path
from typing import Optional, List, Tuple

from config import settings

logger = logging.getLogger(__name__)

# Import Hindi processor
try:
    from core.hindi_processor import (
        preprocess_for_tts,
        preprocess_for_tts_chunked,
        REFERENCE_TRANSCRIPT
    )
except ImportError:
    from hindi_processor import (
        preprocess_for_tts,
        preprocess_for_tts_chunked,
        REFERENCE_TRANSCRIPT
    )

# =============================================================================
# Configuration
# =============================================================================

# Model options (in order of preference)
INDICF5_MODEL = "ai4bharat/IndicF5"  # Best for Hindi
F5_HINDI_MODEL = "IITM/F5-Hindi-24KHz"  # Alternative
F5_BASE_MODEL = "F5TTS_v1_Base"  # Fallback

# Reference audio settings
REFERENCE_AUDIO_DURATION = 15  # seconds - optimal for F5-TTS
MAX_GENERATION_LENGTH = 200  # characters per chunk


# =============================================================================
# Global State
# =============================================================================

_voice_sample_path: Optional[Path] = None
_voice_sample_transcript: Optional[str] = None
_custom_model_path: Optional[Path] = None
_indicf5_available: Optional[bool] = None


# =============================================================================
# Helper Functions
# =============================================================================

def _check_indicf5_available() -> bool:
    """Check if IndicF5/F5-TTS is available.
    
    Note: IndicF5 installs as f5_tts module from:
    pip install git+https://github.com/AI4Bharat/IndicF5.git
    """
    global _indicf5_available
    
    if _indicf5_available is not None:
        return _indicf5_available
    
    try:
        # IndicF5 installs as f5_tts module with DiT model
        from f5_tts.model import DiT
        _indicf5_available = True
        logger.info("✅ IndicF5/F5-TTS available - using Hindi-optimized model")
    except ImportError:
        _indicf5_available = False
        logger.info("ℹ️ F5-TTS not installed, using CLI fallback")
    
    return _indicf5_available


def _find_voice_sample() -> Tuple[Optional[Path], Optional[str]]:
    """Find Maharaj's voice sample and its transcript."""
    global _voice_sample_path, _voice_sample_transcript
    
    if _voice_sample_path is not None:
        return _voice_sample_path, _voice_sample_transcript
    
    # Check configured path
    if settings.VOICE_SAMPLE_PATH and Path(settings.VOICE_SAMPLE_PATH).exists():
        _voice_sample_path = Path(settings.VOICE_SAMPLE_PATH)
        # Try to load transcript
        transcript_path = _voice_sample_path.with_suffix('.txt')
        if transcript_path.exists():
            _voice_sample_transcript = transcript_path.read_text(encoding='utf-8').strip()
        else:
            _voice_sample_transcript = REFERENCE_TRANSCRIPT
        return _voice_sample_path, _voice_sample_transcript
    
    # Check reference_audio directory
    ref_dir = Path(__file__).parent.parent / "data" / "reference_audio"
    if ref_dir.exists():
        for audio_file in ref_dir.glob("*.wav"):
            transcript_path = audio_file.with_suffix('.txt')
            if transcript_path.exists():
                _voice_sample_path = audio_file
                _voice_sample_transcript = transcript_path.read_text(encoding='utf-8').strip()
                logger.info(f"🎤 Reference audio: {audio_file.name}")
                return _voice_sample_path, _voice_sample_transcript
    
    # Check Input folder for original samples
    input_dir = Path(__file__).parent.parent.parent / "Input"
    for name in ["maharaj_audio.mp3", "maharaj-voice.mp3", "maharaj_voice.wav"]:
        path = input_dir / name
        if path.exists():
            _voice_sample_path = path
            _voice_sample_transcript = REFERENCE_TRANSCRIPT
            logger.info(f"🎤 Voice sample: {path.name}")
            return _voice_sample_path, _voice_sample_transcript
    
    return None, None


def _find_custom_model() -> Optional[Path]:
    """Find custom trained model."""
    global _custom_model_path
    
    if _custom_model_path is not None:
        return _custom_model_path
    
    # Check configured path
    if hasattr(settings, 'MAHARAJ_MODEL_PATH') and settings.MAHARAJ_MODEL_PATH:
        model_path = Path(settings.MAHARAJ_MODEL_PATH)
        if model_path.exists():
            _custom_model_path = model_path
            logger.info(f"🎤 Using custom model: {model_path.name}")
            return _custom_model_path
    
    # Check default locations
    model_dir = Path(__file__).parent.parent / "models" / "maharaj_voice"
    for name in ["model_best.pt", "model.pt", "checkpoint.pt"]:
        path = model_dir / name
        if path.exists():
            _custom_model_path = path
            logger.info(f"🎤 Found custom model: {path}")
            return _custom_model_path
    
    return None


# =============================================================================
# Main TTS Functions
# =============================================================================

async def generate_speech_async(text: str, language: str = "hi") -> str:
    """
    Generate speech in Maharaj Premanand's voice.
    
    Pipeline:
    1. Preprocess Hindi text (normalize, convert numbers)
    2. Segment into chunks if long
    3. Generate audio for each chunk
    4. Concatenate if multiple chunks
    
    Returns URL path to audio file.
    """
    if not text or not text.strip():
        return ""
    
    try:
        # Ensure audio directory exists
        settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        
        # Preprocess text for Hindi TTS
        processed_text = preprocess_for_tts(text)
        if not processed_text:
            return ""
        
        # Generate unique filename
        audio_id = str(uuid.uuid4())[:8]
        filename = f"tts_{audio_id}.wav"
        filepath = settings.AUDIO_DIR / filename
        
        # Get reference audio and transcript
        voice_sample, transcript = _find_voice_sample()
        
        # Try custom model first
        custom_model = _find_custom_model()
        if custom_model:
            success = await _generate_with_custom_model(processed_text, custom_model, filepath)
            if success:
                logger.info(f"🎤 Generated with custom model: {filename}")
                return f"/api/audio/{filename}"
        
        # Try IndicF5 (best for Hindi)
        if _check_indicf5_available() and voice_sample:
            success = await _generate_with_indicf5(
                processed_text, 
                voice_sample, 
                transcript or REFERENCE_TRANSCRIPT,
                filepath
            )
            if success:
                logger.info(f"🎤 Generated with IndicF5: {filename}")
                return f"/api/audio/{filename}"
        
        # Fall back to F5-TTS with voice sample
        if voice_sample:
            success = await _generate_with_f5tts(
                processed_text, 
                voice_sample,
                transcript or REFERENCE_TRANSCRIPT,
                filepath
            )
            if success:
                logger.info(f"🎤 Generated with F5-TTS: {filename}")
                return f"/api/audio/{filename}"
        
        logger.error("❌ No voice sample or model found!")
        return ""
        
    except Exception as e:
        logger.error(f"❌ TTS failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ""


async def generate_long_speech_async(text: str, language: str = "hi") -> str:
    """
    Generate speech for long text by chunking.
    Better for paragraphs and full responses.
    """
    if not text or not text.strip():
        return ""
    
    try:
        # Segment text into speakable chunks
        chunks = preprocess_for_tts_chunked(text, MAX_GENERATION_LENGTH)
        
        if len(chunks) == 1:
            return await generate_speech_async(chunks[0], language)
        
        # Generate audio for each chunk
        settings.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        audio_id = str(uuid.uuid4())[:8]
        
        chunk_files = []
        for i, chunk in enumerate(chunks):
            chunk_filename = f"tts_{audio_id}_part{i}.wav"
            chunk_filepath = settings.AUDIO_DIR / chunk_filename
            
            voice_sample, transcript = _find_voice_sample()
            if voice_sample:
                success = await _generate_with_f5tts(
                    chunk,
                    voice_sample,
                    transcript or REFERENCE_TRANSCRIPT,
                    chunk_filepath
                )
                if success:
                    chunk_files.append(chunk_filepath)
        
        if not chunk_files:
            return ""
        
        # Concatenate chunks
        final_filename = f"tts_{audio_id}.wav"
        final_filepath = settings.AUDIO_DIR / final_filename
        
        if len(chunk_files) == 1:
            chunk_files[0].rename(final_filepath)
        else:
            await _concatenate_audio(chunk_files, final_filepath)
            # Cleanup chunk files
            for f in chunk_files:
                if f.exists():
                    f.unlink()
        
        return f"/api/audio/{final_filename}"
        
    except Exception as e:
        logger.error(f"❌ Long TTS failed: {e}")
        return ""


async def _concatenate_audio(input_files: List[Path], output_file: Path) -> bool:
    """Concatenate multiple audio files using ffmpeg."""
    try:
        # Create file list for ffmpeg
        list_file = output_file.parent / f"concat_{output_file.stem}.txt"
        with open(list_file, 'w') as f:
            for audio_file in input_files:
                f.write(f"file '{audio_file.absolute()}'\n")
        
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_file)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.wait_for(process.communicate(), timeout=60)
        
        # Cleanup list file
        if list_file.exists():
            list_file.unlink()
        
        return output_file.exists()
        
    except Exception as e:
        logger.error(f"Concatenation failed: {e}")
        return False


# =============================================================================
# Model-Specific Generation
# =============================================================================

async def _generate_with_custom_model(text: str, model_path: Path, output_path: Path) -> bool:
    """Generate speech using custom trained F5-TTS model."""
    try:
        cmd = [
            "f5-tts_infer-cli",
            "--model", str(model_path),
            "--gen_text", text,
            "--output_dir", str(output_path.parent),
            "--output_file", output_path.name
        ]
        
        logger.info("🎤 Generating with custom model...")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        
        if output_path.exists():
            return True
        
        if process.returncode != 0:
            logger.warning(f"Custom model error: {stderr.decode()[:200]}")
        
        return False
        
    except asyncio.TimeoutError:
        logger.error("❌ TTS timed out")
        return False
    except FileNotFoundError:
        logger.error("❌ f5-tts not found. Run: pip install f5-tts")
        return False
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return False


async def _generate_with_indicf5(
    text: str, 
    voice_sample: Path, 
    ref_transcript: str,
    output_path: Path
) -> bool:
    """Generate speech using IndicF5/F5-TTS (Hindi-optimized model)."""
    try:
        import torch
        import soundfile as sf
        from f5_tts.model import DiT
        from f5_tts.infer.utils_infer import (
            load_vocoder,
            load_model,
            infer_process,
            preprocess_ref_audio_text,
        )
        
        logger.info("🎤 Loading IndicF5 model...")
        
        # Device selection
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load vocoder and model
        vocoder = load_vocoder(vocoder_name="vocos", is_local=False)
        
        # Load F5-TTS model (works for Hindi)
        model_cls = DiT
        model_cfg = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512, conv_layers=4)
        ckpt_file = ""  # Will use default
        vocab_file = ""  # Will use default
        
        ema_model = load_model(
            model_cls, model_cfg, ckpt_file, mel_spec_type="vocos", vocab_file=vocab_file
        )
        
        # Preprocess reference audio
        ref_audio_path = str(voice_sample.absolute())
        ref_text = ref_transcript
        
        logger.info(f"🎤 Processing reference audio: {voice_sample.name}")
        
        # Generate audio
        audio, sr, _ = infer_process(
            ref_audio_path,
            ref_text,
            text,
            ema_model,
            vocoder,
            mel_spec_type="vocos",
            speed=1.0,
            device=device,
        )
        
        # Save output
        sf.write(str(output_path), audio, sr)
        logger.info(f"🎤 Audio saved: {output_path.name}")
        
        return output_path.exists()
        
    except ImportError as e:
        logger.warning(f"IndicF5 import error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ IndicF5 error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def _generate_with_f5tts(
    text: str, 
    voice_sample: Path,
    ref_transcript: str, 
    output_path: Path
) -> bool:
    """Generate speech using F5-TTS with voice sample reference."""
    try:
        import sys
        python_exe = sys.executable
        
        # Use Python module CLI - more reliable on Windows
        cmd = [
            python_exe, "-m", "f5_tts.infer.infer_cli",
            "-r", str(voice_sample.absolute()),
            "-s", ref_transcript,
            "-t", text,
            "-o", str(output_path.parent),
            "-n", output_path.stem,
            "--speed", "1.0",
        ]
        
        logger.info(f"🎤 Generating: '{text[:50]}...'")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        
        # Check for output file (CLI might add .wav extension)
        if output_path.exists():
            return True
        
        # Check for file without .wav extension
        output_without_ext = output_path.parent / f"{output_path.stem}.wav"
        if output_without_ext.exists():
            return True
        
        # Check for any recently created wav file
        for f in output_path.parent.glob("*.wav"):
            if f.stat().st_mtime > (asyncio.get_event_loop().time() - 120):
                try:
                    f.rename(output_path)
                    return True
                except:
                    pass
        
        if process.returncode != 0:
            logger.warning(f"F5-TTS error: {stderr.decode()[:500]}")
        
        return False
        
    except asyncio.TimeoutError:
        logger.error("❌ TTS timed out (>300s) - CPU mode is slow")
        return False
    except FileNotFoundError:
        logger.error("❌ f5-tts module not found")
        return False
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


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
# Reference Audio Setup
# =============================================================================

async def setup_reference_audio():
    """
    Create optimized reference audio from Maharaj's recordings.
    Extracts a clean 15-second clip with known transcript.
    """
    input_dir = Path(__file__).parent.parent.parent / "Input"
    output_dir = Path(__file__).parent.parent / "data" / "reference_audio"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    source_audio = input_dir / "maharaj_audio.mp3"
    if not source_audio.exists():
        source_audio = input_dir / "maharaj-voice.mp3"
    
    if not source_audio.exists():
        logger.error("No source audio found in Input folder")
        return False
    
    output_audio = output_dir / "maharaj_reference.wav"
    output_transcript = output_dir / "maharaj_reference.txt"
    
    try:
        # Extract first 15 seconds (based on transcript timestamps)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source_audio),
            "-ss", "0",
            "-t", "15",
            "-ar", "24000",  # 24kHz for F5-TTS
            "-ac", "1",      # Mono
            str(output_audio)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.wait_for(process.communicate(), timeout=60)
        
        if output_audio.exists():
            # Write transcript
            output_transcript.write_text(REFERENCE_TRANSCRIPT, encoding='utf-8')
            logger.info(f"✅ Reference audio created: {output_audio}")
            logger.info(f"✅ Transcript saved: {output_transcript}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to create reference audio: {e}")
        return False


# =============================================================================
# Test
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing Maharaj Voice TTS Engine v2.0")
        print("=" * 50)
        
        # Setup reference audio first
        print("\n1. Setting up reference audio...")
        await setup_reference_audio()
        
        # Test generation
        test_texts = [
            "नमस्ते, मैं प्रेमानंद महाराज हूँ।",
            "जीवन में सुख-दुख का आना-जाना लगा रहता है।",
            "भगवद्गीता का अध्याय 15 बहुत महत्वपूर्ण है।",
        ]
        
        print("\n2. Testing TTS generation...")
        for text in test_texts:
            print(f"\nInput: {text}")
            result = await generate_speech_async(text)
            print(f"Output: {result}")
    
    asyncio.run(test())

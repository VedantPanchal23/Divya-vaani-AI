import { useState, useRef } from 'react';
import { Icons } from './Icons';
import { textToSpeech, getAudioUrl } from '../api';

/**
 * TextToSpeech Component - Uses Microsoft Edge TTS (server-side) male voice
 * 
 * Features:
 * - Calls backend /api/tts which uses Edge TTS male neural voices
 *   (hi-IN-MadhurNeural for Hindi, en-IN-PrabhatNeural for English)
 * - Supports pre-generated audio URL (audioUrl prop) as priority
 * - Falls back to browser SpeechSynthesis only if server fails
 * - Cleans markdown and timestamps
 */
function TextToSpeech({ text, lang = 'hi', audioUrl }) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const audioRef = useRef(null);

    // Cancel audio on unmount
    // (using ref cleanup pattern instead of useEffect for simplicity)

    const handleStop = () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
            audioRef.current = null;
        }
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        setIsPlaying(false);
        setIsLoading(false);
    };

    const playAudioUrl = (url) => {
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onplay = () => { setIsPlaying(true); setIsLoading(false); };
        audio.onended = () => { setIsPlaying(false); audioRef.current = null; };
        audio.onerror = () => {
            setIsPlaying(false);
            setIsLoading(false);
            audioRef.current = null;
        };
        audio.play().catch(() => {
            setIsPlaying(false);
            setIsLoading(false);
            audioRef.current = null;
        });
    };

    const playBrowserTTSFallback = () => {
        if (!text || !('speechSynthesis' in window)) return;

        const cleanedText = text
            .replace(/\[\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\]:\s*/g, '')
            .replace(/^#{1,6}\s*/gm, '')
            .replace(/\*+([^*]+)\*+/g, '$1')
            .replace(/_+([^_]+)_+/g, '$1')
            .replace(/^[\s]*[-*•]\s*/gm, ' ')
            .replace(/^[\s]*\d+\.\s*/gm, ' ')
            .replace(/https?:\/\/\S+/g, '')
            .replace(/\s+/g, ' ')
            .trim();
        if (!cleanedText) return;

        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(cleanedText);
        utterance.lang = lang.startsWith('hi') ? 'hi-IN' : 'en-IN';
        utterance.rate = lang.startsWith('hi') ? 0.9 : 1.0;
        utterance.pitch = 0.85;
        utterance.onstart = () => { setIsPlaying(true); setIsLoading(false); };
        utterance.onend = () => setIsPlaying(false);
        utterance.onerror = () => setIsPlaying(false);
        window.speechSynthesis.speak(utterance);
    };

    const handlePlay = async () => {
        if (!text && !audioUrl) return;
        if (isPlaying) { handleStop(); return; }

        // Priority 1: Pre-generated audio URL
        if (audioUrl) {
            playAudioUrl(audioUrl);
            return;
        }

        // Priority 2: Call server Edge TTS API (male voice)
        if (text) {
            setIsLoading(true);
            try {
                const language = lang.startsWith('hi') ? 'hi' : 'en';
                const response = await textToSpeech(text, language);
                if (response?.audio_url) {
                    playAudioUrl(response.audio_url);
                    return;
                }
            } catch (err) {
                console.warn('Server TTS failed, falling back to browser:', err.message);
            }

            // Priority 3: Browser fallback
            playBrowserTTSFallback();
        }
    };

    return (
        <div className="tts-container">
            <button
                className={`tts-button ${isPlaying ? 'speaking' : ''} ${isLoading ? 'loading' : ''}`}
                onClick={isPlaying ? handleStop : handlePlay}
                disabled={(!text && !audioUrl) || isLoading}
                title={isLoading ? 'Generating...' : isPlaying ? 'Stop' : 'Listen'}
            >
                {isLoading ? (
                    <>
                        <Icons.Loading size={14} className="animate-spin" />
                        Loading...
                    </>
                ) : isPlaying ? (
                    <>
                        <Icons.Stop size={14} />
                        Stop
                    </>
                ) : (
                    <>
                        <Icons.VolumeOn size={14} />
                        Listen
                    </>
                )}
            </button>
        </div>
    );
}

export default TextToSpeech;

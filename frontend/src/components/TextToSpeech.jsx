import { useState, useEffect, useRef } from 'react';
import { Icons } from './Icons';

/**
 * TextToSpeech Component - Uses Browser's Built-in Speech Synthesis
 * 
 * Features:
 * - Supports server-side audio URL (audioUrl prop) as priority
 * - Instant browser playback as fallback (no server calls)
 * - Reads full text with chunk-based workaround for Chrome 15s bug
 * - Supports Hindi and English
 * - Cleans markdown and timestamps
 */
function TextToSpeech({ text, lang = 'hi', audioUrl }) {
    const [isPlaying, setIsPlaying] = useState(false);
    const [voices, setVoices] = useState([]);
    const audioRef = useRef(null);
    const utteranceRef = useRef(null);
    const resumeTimerRef = useRef(null);

    // Load available voices
    useEffect(() => {
        const loadVoices = () => {
            const availableVoices = window.speechSynthesis?.getVoices() || [];
            setVoices(availableVoices);
        };

        loadVoices();
        
        // Chrome loads voices asynchronously
        if (window.speechSynthesis) {
            window.speechSynthesis.addEventListener('voiceschanged', loadVoices);
        }

        return () => {
            if (window.speechSynthesis) {
                window.speechSynthesis.removeEventListener('voiceschanged', loadVoices);
            }
        };
    }, []);

    // Cancel speech on unmount
    useEffect(() => {
        return () => {
            if (window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            if (audioRef.current) {
                audioRef.current.pause();
                audioRef.current = null;
            }
            if (resumeTimerRef.current) {
                clearInterval(resumeTimerRef.current);
            }
        };
    }, []);

    // Clean text for TTS
    const cleanText = (rawText) => {
        if (!rawText) return '';
        return rawText
            // Remove timestamps like [03:43 - 04:13]:
            .replace(/\[\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\]:\s*/g, '')
            // Remove markdown headers
            .replace(/^#{1,6}\s*/gm, '')
            // Remove bold/italic
            .replace(/\*+([^*]+)\*+/g, '$1')
            .replace(/_+([^_]+)_+/g, '$1')
            // Remove bullet points
            .replace(/^[\s]*[-*•]\s*/gm, ' ')
            // Remove numbered lists  
            .replace(/^[\s]*\d+\.\s*/gm, ' ')
            // Remove URLs
            .replace(/https?:\/\/\S+/g, '')
            // Normalize whitespace
            .replace(/\s+/g, ' ')
            .trim();
    };

    // Find best voice for language
    const getBestVoice = (targetLang) => {
        const langCode = targetLang.startsWith('hi') ? 'hi' : 'en';
        
        // Priority: Google voices > Microsoft voices > Any matching voice
        const googleVoice = voices.find(v => 
            v.lang.startsWith(langCode) && v.name.toLowerCase().includes('google')
        );
        if (googleVoice) return googleVoice;

        const msVoice = voices.find(v => 
            v.lang.startsWith(langCode) && v.name.toLowerCase().includes('microsoft')
        );
        if (msVoice) return msVoice;

        // Any voice matching the language
        return voices.find(v => v.lang.startsWith(langCode));
    };

    const handlePlay = () => {
        if (!text && !audioUrl) return;

        // If playing, stop
        if (isPlaying) {
            handleStop();
            return;
        }

        // Priority 1: Server-side audio URL
        if (audioUrl) {
            const audio = new Audio(audioUrl);
            audioRef.current = audio;
            audio.onplay = () => setIsPlaying(true);
            audio.onended = () => { setIsPlaying(false); audioRef.current = null; };
            audio.onerror = () => {
                // Fallback to browser TTS if audio fails
                setIsPlaying(false);
                audioRef.current = null;
                playBrowserTTS();
            };
            audio.play().catch(() => {
                audioRef.current = null;
                playBrowserTTS();
            });
            return;
        }

        // Priority 2: Browser SpeechSynthesis
        playBrowserTTS();
    };

    const playBrowserTTS = () => {
        if (!text || !('speechSynthesis' in window)) {
            console.error('Speech synthesis not supported');
            return;
        }

        // Clean and prepare text
        const cleanedText = cleanText(text);
        if (!cleanedText) return;

        // Cancel any ongoing speech
        window.speechSynthesis.cancel();
        if (resumeTimerRef.current) {
            clearInterval(resumeTimerRef.current);
        }

        // Create utterance
        const utterance = new SpeechSynthesisUtterance(cleanedText);
        utteranceRef.current = utterance;
        
        // Set language
        const isHindi = lang.startsWith('hi');
        utterance.lang = isHindi ? 'hi-IN' : 'en-IN';
        
        // Set voice
        const bestVoice = getBestVoice(lang);
        if (bestVoice) {
            utterance.voice = bestVoice;
        }

        // Settings for natural speech
        utterance.rate = isHindi ? 0.9 : 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        // Event handlers
        utterance.onstart = () => setIsPlaying(true);
        utterance.onend = () => {
            setIsPlaying(false);
            if (resumeTimerRef.current) {
                clearInterval(resumeTimerRef.current);
                resumeTimerRef.current = null;
            }
        };
        utterance.onerror = (e) => {
            if (e.error !== 'canceled') {
                console.error('TTS Error:', e);
            }
            setIsPlaying(false);
            if (resumeTimerRef.current) {
                clearInterval(resumeTimerRef.current);
                resumeTimerRef.current = null;
            }
        };

        // Speak
        window.speechSynthesis.speak(utterance);

        // Chrome workaround: Chrome pauses SpeechSynthesis after ~15 seconds.
        // Calling pause() then resume() every 10s keeps it alive.
        resumeTimerRef.current = setInterval(() => {
            if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
                window.speechSynthesis.pause();
                window.speechSynthesis.resume();
            } else if (!window.speechSynthesis.speaking) {
                clearInterval(resumeTimerRef.current);
                resumeTimerRef.current = null;
            }
        }, 10000);
    };

    const handleStop = () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
        }
        if (resumeTimerRef.current) {
            clearInterval(resumeTimerRef.current);
            resumeTimerRef.current = null;
        }
        setIsPlaying(false);
    };

    // Check if browser supports speech synthesis or we have an audio URL
    const isSupported = audioUrl || 'speechSynthesis' in window;

    if (!isSupported) {
        return null; // Don't show button if not supported
    }

    return (
        <div className="tts-container">
            <button
                className={`tts-button ${isPlaying ? 'speaking' : ''}`}
                onClick={isPlaying ? handleStop : handlePlay}
                disabled={!text && !audioUrl}
                title={isPlaying ? 'Stop' : 'Listen'}
            >
                {isPlaying ? (
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

import { useState, useRef, useEffect } from 'react';
import { Icons } from './Icons';

const API_BASE = '';  // Uses Vite proxy

function TextToSpeech({ text, lang = 'hi', audioUrl = null }) {
    const [isLoading, setIsLoading] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [error, setError] = useState(null);
    const [cachedUrl, setCachedUrl] = useState(null);
    const audioRef = useRef(null);

    // Use pre-generated audio URL if provided
    useEffect(() => {
        if (audioUrl) {
            setCachedUrl(audioUrl.startsWith('/') ? audioUrl : `/${audioUrl}`);
        }
    }, [audioUrl]);

    const generateAndPlay = async () => {
        if (!text || isLoading) return;

        // If already playing, stop
        if (isPlaying && audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
            setIsPlaying(false);
            return;
        }

        // Use cached URL if available (pre-generated from backend)
        if (cachedUrl && audioRef.current) {
            try {
                audioRef.current.src = cachedUrl;
                audioRef.current.load();
                await audioRef.current.play();
                setIsPlaying(true);
                return;
            } catch (err) {
                console.warn('Cached audio failed, regenerating...', err);
                setCachedUrl(null);
            }
        }

        setIsLoading(true);
        setError(null);

        try {
            // Call server-side TTS API (correct endpoint)
            const response = await fetch(`${API_BASE}/api/tts`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: text,
                    language: lang.startsWith('hi') ? 'hi' : 'en'
                }),
            });

            if (!response.ok) {
                throw new Error('TTS generation failed');
            }

            const data = await response.json();
            const url = data.audio_url.startsWith('/') ? data.audio_url : `/${data.audio_url}`;
            setCachedUrl(url);

            // Create audio element and play
            if (audioRef.current) {
                audioRef.current.src = url;
                audioRef.current.load();
                await audioRef.current.play();
                setIsPlaying(true);
            }
        } catch (err) {
            console.error('TTS Error:', err);
            setError('Audio generation failed');

            // Fallback to browser TTS
            fallbackToSpeechSynthesis();
        } finally {
            setIsLoading(false);
        }
    };

    const fallbackToSpeechSynthesis = () => {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = lang;
            utterance.rate = 0.9;
            utterance.onstart = () => setIsPlaying(true);
            utterance.onend = () => setIsPlaying(false);
            utterance.onerror = () => setIsPlaying(false);
            window.speechSynthesis.speak(utterance);
        }
    };

    const handleAudioEnded = () => {
        setIsPlaying(false);
    };

    const handleStop = () => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current.currentTime = 0;
        }
        window.speechSynthesis?.cancel();
        setIsPlaying(false);
    };

    return (
        <div className="tts-container">
            <button
                className={`tts-button ${isPlaying ? 'speaking' : ''} ${isLoading ? 'loading' : ''}`}
                onClick={isPlaying ? handleStop : generateAndPlay}
                disabled={isLoading || !text}
                title={isPlaying ? 'Stop' : 'Listen to Maharaj\'s Voice'}
            >
                {isLoading ? (
                    <>
                        <Icons.Loading size={14} className="animate-spin" />
                        Generating...
                    </>
                ) : isPlaying ? (
                    <>
                        <Icons.Stop size={14} />
                        Stop
                    </>
                ) : (
                    <>
                        <Icons.VolumeOn size={14} />
                        🙏 Listen
                    </>
                )}
            </button>

            {error && (
                <span className="tts-error" title={error}>
                    <Icons.Error size={14} />
                </span>
            )}

            {/* Hidden audio element */}
            <audio
                ref={audioRef}
                onEnded={handleAudioEnded}
                onError={() => {
                    setError('Audio playback failed');
                    setIsPlaying(false);
                }}
                style={{ display: 'none' }}
            />
        </div>
    );
}

export default TextToSpeech;

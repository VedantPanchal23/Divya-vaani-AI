import { useState, useEffect, useRef, useCallback } from 'react';
import { sendMessage } from '../api';
import { Icons } from './Icons';
import TextToSpeech from './TextToSpeech';

// Detect browser Speech Recognition support
function getSpeechRecognition() {
    if (typeof window === 'undefined') return null;
    return window.SpeechRecognition
        || window.webkitSpeechRecognition
        || window.mozSpeechRecognition
        || window.msSpeechRecognition
        || null;
}

function Chat({ sessionId, onNewMessage }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [outputLanguage, setOutputLanguage] = useState('auto');
    const [isListening, setIsListening] = useState(false);
    const [micError, setMicError] = useState(null);
    const [interimText, setInterimText] = useState('');
    const [micSupported, setMicSupported] = useState(false);
    const [micLevel, setMicLevel] = useState(0); // 0-100 for visual feedback
    const messagesEndRef = useRef(null);
    const inputRef = useRef(null);
    const recognitionRef = useRef(null);
    const baseInputRef = useRef(''); // track input before speech started
    const wantListeningRef = useRef(false); // true when user wants mic on
    const inputRef2 = useRef(''); // always-current input value for closure safety
    const streamRef = useRef(null);
    const audioCtxRef = useRef(null);
    const animFrameRef = useRef(null);

    // Check speech support on mount
    useEffect(() => {
        const SR = getSpeechRecognition();
        setMicSupported(!!SR);
        if (!SR) {
            console.warn('[Speech] SpeechRecognition API not available in this browser');
        } else {
            console.log('[Speech] SpeechRecognition API available:', SR.name || 'webkitSpeechRecognition');
        }
    }, []);

    // Keep input ref in sync
    useEffect(() => { inputRef2.current = input; }, [input]);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            wantListeningRef.current = false;
            cancelAnimationFrame(animFrameRef.current);
            if (recognitionRef.current) {
                try { recognitionRef.current.abort(); } catch {}
                recognitionRef.current = null;
            }
            if (streamRef.current) {
                streamRef.current.getTracks().forEach(t => t.stop());
                streamRef.current = null;
            }
            if (audioCtxRef.current) {
                try { audioCtxRef.current.close(); } catch {}
                audioCtxRef.current = null;
            }
        };
    }, []);

    // ===== Start mic audio level monitoring (visual feedback) =====
    const startMicMonitor = useCallback(async () => {
        try {
            // List available audio devices for debugging
            const devices = await navigator.mediaDevices.enumerateDevices();
            const mics = devices.filter(d => d.kind === 'audioinput');
            console.log('[Mic] Available microphones:', mics.map(m => `${m.label || 'unnamed'} (${m.deviceId.slice(0,8)})`));

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                }
            });
            streamRef.current = stream;

            // Log which mic track we got
            const audioTrack = stream.getAudioTracks()[0];
            console.log('[Mic] Using track:', audioTrack.label, '| enabled:', audioTrack.enabled, '| muted:', audioTrack.muted, '| readyState:', audioTrack.readyState);

            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            // CRITICAL: Resume AudioContext (Chrome suspends it by default)
            if (audioCtx.state === 'suspended') {
                await audioCtx.resume();
                console.log('[Mic] AudioContext resumed from suspended state');
            }
            console.log('[Mic] AudioContext state:', audioCtx.state, '| sampleRate:', audioCtx.sampleRate);

            const source = audioCtx.createMediaStreamSource(stream);
            const analyser = audioCtx.createAnalyser();
            analyser.fftSize = 2048;
            analyser.smoothingTimeConstant = 0.3;
            source.connect(analyser);
            audioCtxRef.current = audioCtx;

            // Use time-domain data (more reliable than frequency data for detecting any sound)
            const dataArray = new Uint8Array(analyser.fftSize);
            let logCounter = 0;
            const poll = () => {
                if (!wantListeningRef.current) return;
                analyser.getByteTimeDomainData(dataArray);
                // Calculate RMS level from waveform (centered at 128)
                let sumSq = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    const val = (dataArray[i] - 128) / 128;
                    sumSq += val * val;
                }
                const rms = Math.sqrt(sumSq / dataArray.length);
                const level = Math.min(100, Math.round(rms * 300)); // scale up for visibility
                setMicLevel(level);

                // Log every ~2 seconds for debugging
                logCounter++;
                if (logCounter % 120 === 0) {
                    console.log('[Mic] Level:', level, '| raw RMS:', rms.toFixed(4), '| AudioCtx:', audioCtx.state);
                }

                animFrameRef.current = requestAnimationFrame(poll);
            };
            animFrameRef.current = requestAnimationFrame(poll);
            console.log('[Mic] Audio level monitor started (time-domain mode)');
        } catch (err) {
            console.error('[Mic] Could not start audio monitor:', err.name, err.message);
            setMicError('Mic access failed: ' + err.message);
            setTimeout(() => setMicError(null), 5000);
        }
    }, []);

    const stopMicMonitor = useCallback(() => {
        cancelAnimationFrame(animFrameRef.current);
        setMicLevel(0);
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(t => t.stop());
            streamRef.current = null;
        }
        if (audioCtxRef.current) {
            try { audioCtxRef.current.close(); } catch {}
            audioCtxRef.current = null;
        }
    }, []);

    // ===== Start browser speech recognition =====
    const startListening = useCallback(() => {
        const SR = getSpeechRecognition();
        if (!SR) {
            setMicError('Speech recognition not supported. Use Google Chrome or Microsoft Edge.');
            setTimeout(() => setMicError(null), 5000);
            return;
        }

        // Abort any existing instance
        if (recognitionRef.current) {
            try { recognitionRef.current.abort(); } catch {}
            recognitionRef.current = null;
        }

        setMicError(null);
        setInterimText('');
        wantListeningRef.current = true;
        baseInputRef.current = inputRef2.current; // use ref for closure safety

        const recognition = new SR();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        // Set language — default to Hindi for this app
        if (outputLanguage === 'en') {
            recognition.lang = 'en-US';
        } else {
            // Auto or Hindi → use Hindi
            recognition.lang = 'hi-IN';
        }

        recognition.onstart = () => {
            setIsListening(true);
            console.log('[Speech] Started, lang:', recognition.lang);
        };

        recognition.onaudiostart = () => {
            console.log('[Speech] Audio capture started — mic is active');
        };

        recognition.onsoundstart = () => {
            console.log('[Speech] Sound detected');
        };

        recognition.onspeechstart = () => {
            console.log('[Speech] Speech detected');
        };

        recognition.onresult = (event) => {
            let finalTranscript = '';
            let interimTranscript = '';

            for (let i = 0; i < event.results.length; i++) {
                const result = event.results[i];
                if (result.isFinal) {
                    finalTranscript += result[0].transcript;
                } else {
                    interimTranscript += result[0].transcript;
                }
            }

            const base = baseInputRef.current.trim();

            if (finalTranscript) {
                const combined = base ? base + ' ' + finalTranscript.trim() : finalTranscript.trim();
                setInput(combined);
                baseInputRef.current = combined;
                setInterimText(interimTranscript);
                console.log('[Speech] Final:', finalTranscript.trim());
            }

            if (interimTranscript) {
                setInterimText(interimTranscript);
                console.log('[Speech] Interim:', interimTranscript);
            }
        };

        recognition.onerror = (event) => {
            console.error('[Speech] Error:', event.error, event.message);
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                setMicError('Microphone blocked! Click the lock icon in address bar → Allow microphone.');
                wantListeningRef.current = false;
                setIsListening(false);
                stopMicMonitor();
            } else if (event.error === 'no-speech') {
                // Chrome fires this after ~5s of silence — auto-restart via onend
                console.log('[Speech] No speech detected, will auto-restart...');
            } else if (event.error === 'audio-capture') {
                setMicError('No microphone found. Connect a mic and try again.');
                wantListeningRef.current = false;
                setIsListening(false);
                stopMicMonitor();
            } else if (event.error === 'network') {
                setMicError('Network error — speech recognition needs internet.');
                wantListeningRef.current = false;
                setIsListening(false);
                stopMicMonitor();
            } else if (event.error === 'aborted') {
                return;
            } else {
                setMicError(`Speech error: ${event.error}`);
                wantListeningRef.current = false;
                setIsListening(false);
                stopMicMonitor();
            }
        };

        recognition.onend = () => {
            console.log('[Speech] Recognition ended, wantListening:', wantListeningRef.current);
            recognitionRef.current = null;
            if (wantListeningRef.current) {
                console.log('[Speech] Auto-restarting...');
                setTimeout(() => {
                    if (wantListeningRef.current) startListening();
                }, 300);
            } else {
                setIsListening(false);
                setInterimText('');
                stopMicMonitor();
                inputRef.current?.focus();
            }
        };

        recognitionRef.current = recognition;

        // Start audio level monitor for visual feedback
        if (!streamRef.current) startMicMonitor();

        try {
            recognition.start();
            console.log('[Speech] recognition.start() called');
        } catch (err) {
            console.error('[Speech] Failed to start:', err);
            setMicError('Failed to start: ' + err.message);
            setTimeout(() => setMicError(null), 5000);
            setIsListening(false);
            wantListeningRef.current = false;
            stopMicMonitor();
        }
    }, [outputLanguage, startMicMonitor, stopMicMonitor]);

    // ===== Stop recognition =====
    const stopListening = useCallback(() => {
        wantListeningRef.current = false;
        if (recognitionRef.current) {
            try {
                recognitionRef.current.stop();
                console.log('[Speech] Manually stopped');
            } catch {}
        }
        setIsListening(false);
        setInterimText('');
        stopMicMonitor();
    }, []);

    const toggleListening = useCallback(() => {
        if (isListening) {
            stopListening();
        } else {
            startListening();
        }
    }, [isListening, startListening, stopListening]);

    const handleSend = async () => {
        if (!input.trim() || isLoading) return;

        // Stop listening if active
        if (isListening) {
            stopListening();
        }

        const userMessage = {
            id: Date.now().toString(),
            role: 'user',
            content: input.trim(),
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsLoading(true);

        try {
            // Auto-detect language based on input text
            let lang = outputLanguage;
            if (outputLanguage === 'auto') {
                // Detect if input has Hindi characters
                lang = detectHindi(userMessage.content) ? 'hi' : 'en';
            }
            const response = await sendMessage(userMessage.content, sessionId, lang);

            const assistantMessage = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: response.answer,
                source: response.source_type,
                sourceRef: response.source_reference,
                audioUrl: response.audio_url,
            };

            setMessages(prev => [...prev, assistantMessage]);
            onNewMessage?.();
        } catch (err) {
            const errorMessage = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: `Sorry, I couldn't process your question. ${err.message}`,
                isError: true,
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleClear = async () => {
        if (confirm('Clear all chat history?')) {
            setMessages([]);
        }
    };

    const detectHindi = (text) => {
        const hindiRegex = /[\u0900-\u097F]/;
        return hindiRegex.test(text);
    };

    return (
        <div className="chat-container">
            {/* Language Selector & Clear Button */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 'var(--spacing-sm)',
                gap: 'var(--spacing-sm)'
            }}>
                <div className="language-selector">
                    <label style={{
                        fontSize: '0.75rem',
                        color: 'var(--color-text-muted)',
                        marginRight: 'var(--spacing-xs)'
                    }}>
                        <Icons.Globe size={12} style={{ marginRight: '4px' }} />
                        Output:
                    </label>
                    <select
                        value={outputLanguage}
                        onChange={(e) => setOutputLanguage(e.target.value)}
                        className="language-select"
                    >
                        <option value="auto">Auto Detect</option>
                        <option value="en">English</option>
                        <option value="hi">हिंदी (Hindi)</option>
                    </select>
                </div>

                {messages.length > 0 && (
                    <button
                        className="btn btn-ghost btn-sm"
                        onClick={handleClear}
                    >
                        <Icons.Delete size={14} />
                        Clear
                    </button>
                )}
            </div>

            {/* Messages */}
            <div className="chat-messages">
                {messages.length === 0 ? (
                    <div className="empty-state" style={{ flex: 1 }}>
                        <Icons.Chat size={32} style={{ opacity: 0.4, marginBottom: '0.5rem' }} />
                        <p style={{ color: 'var(--color-text-muted)', marginTop: '0.5rem' }}>
                            Ask anything about the speech
                        </p>
                        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                            {micSupported ? 'Type or tap the mic button — it auto-stops when you pause' : 'Type your question below'}
                        </p>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={`chat-message ${msg.role} ${detectHindi(msg.content) ? 'hindi' : ''}`}
                        >
                            <p style={{
                                fontFamily: detectHindi(msg.content) ? 'var(--font-hindi)' : 'inherit'
                            }}>
                                {msg.content}
                            </p>

                            {/* Relevant quotes */}
                            {msg.quotes && msg.quotes.length > 0 && (
                                <div style={{
                                    marginTop: 'var(--spacing-sm)',
                                    padding: 'var(--spacing-sm)',
                                    background: 'var(--color-bg-tertiary)',
                                    borderRadius: 'var(--radius-sm)',
                                    fontSize: '0.85rem',
                                    border: '1px solid var(--border-color)'
                                }}>
                                    <strong style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                        <Icons.BookOpen size={14} />
                                        From the speech:
                                    </strong>
                                    {msg.quotes.map((quote, i) => (
                                        <p key={i} style={{ marginTop: '0.25rem', fontStyle: 'italic' }}>
                                            "{quote}"
                                        </p>
                                    ))}
                                </div>
                            )}

                            {/* TTS Listen Button for Assistant Messages */}
                            {msg.role === 'assistant' && !msg.isError && (
                                <div style={{ marginTop: 'var(--spacing-sm)' }}>
                                    <TextToSpeech 
                                        text={msg.content} 
                                        lang={detectHindi(msg.content) ? 'hi' : 'en'}
                                        audioUrl={msg.audioUrl}
                                    />
                                </div>
                            )}
                        </div>
                    ))
                )}

                {isLoading && (
                    <div className="chat-message assistant">
                        <div className="loading-text" style={{ gap: 'var(--spacing-sm)' }}>
                            <Icons.Loading size={20} className="animate-spin" />
                            <span>Thinking...</span>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Mic error message */}
            {micError && (
                <div style={{
                    padding: '6px 12px',
                    marginBottom: '6px',
                    fontSize: '0.8rem',
                    color: 'var(--color-error, #e74c3c)',
                    background: 'var(--color-bg-tertiary)',
                    borderRadius: 'var(--radius-sm)',
                    textAlign: 'center'
                }}>
                    {micError}
                </div>
            )}

            {/* Listening indicator */}
            {isListening && (
                <div style={{
                    padding: '8px 12px',
                    marginBottom: '6px',
                    fontSize: '0.8rem',
                    color: 'var(--color-text-muted)',
                    background: 'var(--color-bg-tertiary)',
                    borderRadius: 'var(--radius-sm)',
                    textAlign: 'center',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                        <span style={{ display: 'inline-block', animation: 'pulse 1.5s infinite' }}><Icons.Mic size={16} /></span>
                        <span>Listening...</span>
                        <div style={{
                            width: '80px',
                            height: '6px',
                            background: 'var(--color-bg-secondary, #e0e0e0)',
                            borderRadius: '3px',
                            overflow: 'hidden'
                        }}>
                            <div style={{
                                width: `${micLevel}%`,
                                height: '100%',
                                background: micLevel > 40 ? '#27ae60' : micLevel > 15 ? '#f39c12' : '#e74c3c',
                                borderRadius: '3px',
                                transition: 'width 0.1s ease'
                            }} />
                        </div>
                    </div>
                    {interimText && (
                        <div style={{ fontSize: '0.85rem', marginTop: '6px', fontStyle: 'italic', color: 'var(--color-accent-primary, #3498db)' }}>
                            "{interimText}"
                        </div>
                    )}
                    <div style={{ fontSize: '0.7rem', marginTop: '3px', opacity: 0.7 }}>
                        {micLevel > 5
                            ? <span><span style={{color:'#27ae60'}}>●</span> Mic active — speak clearly</span>
                            : <span><span style={{color:'#e74c3c'}}>●</span> No audio — check: Windows Settings → Privacy → Microphone → Allow apps to access mic</span>}
                    </div>
                </div>
            )}

            {/* Input with Voice */}
            <div className="chat-input-container">
                {micSupported ? (
                    <button
                        className={`btn btn-icon voice-btn ${isListening ? 'listening' : ''}`}
                        onClick={toggleListening}
                        title={isListening ? 'Click to stop listening' : 'Click to speak'}
                        disabled={isLoading}
                        type="button"
                        style={isListening ? { background: '#e74c3c', color: '#fff' } : {}}
                    >
                        <Icons.Mic size={18} />
                    </button>
                ) : (
                    <button
                        className="btn btn-icon voice-btn"
                        onClick={() => {
                            setMicError('Speech recognition requires Google Chrome or Microsoft Edge browser.');
                            setTimeout(() => setMicError(null), 5000);
                        }}
                        title="Speech recognition not supported in this browser"
                        type="button"
                        style={{ opacity: 0.4 }}
                    >
                        <Icons.Mic size={18} />
                    </button>
                )}
                <input
                    ref={inputRef}
                    className="chat-input"
                    type="text"
                    placeholder={isListening ? 'Listening... speak now' : (outputLanguage === 'hi' ? 'हिंदी में पूछें...' : 'Ask in Hindi or English...')}
                    value={isListening && interimText ? input + (input ? ' ' : '') + interimText : input}
                    onChange={(e) => { if (!isListening) setInput(e.target.value); }}
                    onKeyDown={handleKeyDown}
                    disabled={isLoading}
                    autoComplete="off"
                />
                <button
                    className="btn btn-primary btn-icon"
                    onClick={handleSend}
                    disabled={!input.trim() || isLoading}
                    type="button"
                    title="Send message"
                >
                    {isLoading ? <Icons.Loading size={18} className="animate-spin" /> : <Icons.Send size={18} />}
                </button>
            </div>
        </div>
    );
}

export default Chat;

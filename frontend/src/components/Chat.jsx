import { useState, useEffect, useRef, useCallback } from 'react';
import { sendMessage, getChatHistory, clearChatHistoryApi } from '../api';
import { Icons } from './Icons';
import TextToSpeech from './TextToSpeech';
import { useAuth } from './AuthContext';

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
    const { isAuthenticated } = useAuth();
    const chatKey = `chat_${sessionId}`;
    const [messages, setMessages] = useState(() => {
        // Authenticated users load from DB in useEffect; start empty
        if (localStorage.getItem('dv_access_token')) return [];
        try {
            const saved = localStorage.getItem(chatKey);
            return saved ? JSON.parse(saved) : [];
        } catch { return []; }
    });
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [outputLanguage, setOutputLanguage] = useState('auto');
    const [isListening, setIsListening] = useState(false);
    const [micError, setMicError] = useState(null);
    const [interimText, setInterimText] = useState('');
    const [micSupported, setMicSupported] = useState(false);
    const [micLevel, setMicLevel] = useState(0); // 0-100 for visual feedback
    const [confirmingClear, setConfirmingClear] = useState(false);
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
        } else {
        }
    }, []);

    // Load chat history from DB when authenticated
    useEffect(() => {
        if (isAuthenticated && sessionId) {
            setHistoryLoading(true);
            getChatHistory(sessionId).then(data => {
                if (data?.messages?.length > 0) {
                    const mapped = data.messages.map(msg => ({
                        id: msg.id,
                        role: msg.role,
                        content: msg.content,
                        source: msg.source_type,
                        sourceRef: msg.source_reference,
                        audioUrl: msg.audio_url,
                    }));
                    setMessages(mapped);
                }
            }).catch(err => {
                console.warn('Failed to load chat history:', err.message);
                // Fall back to localStorage if DB fails
                try {
                    const saved = localStorage.getItem(chatKey);
                    if (saved) setMessages(JSON.parse(saved));
                } catch {}
            }).finally(() => setHistoryLoading(false));
        }
    }, [isAuthenticated, sessionId]);

    // Keep input ref in sync
    useEffect(() => { inputRef2.current = input; }, [input]);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Persist messages to localStorage (anonymous users only — authenticated use DB)
    useEffect(() => {
        if (isAuthenticated) return; // DB handles persistence for logged-in users
        try {
            if (messages.length > 0) {
                localStorage.setItem(chatKey, JSON.stringify(messages));
            } else {
                localStorage.removeItem(chatKey);
            }
        } catch { /* quota exceeded — ignore */ }
    }, [messages, chatKey, isAuthenticated]);

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

            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            // CRITICAL: Resume AudioContext (Chrome suspends it by default)
            if (audioCtx.state === 'suspended') {
                await audioCtx.resume();
            }

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
                }

                animFrameRef.current = requestAnimationFrame(poll);
            };
            animFrameRef.current = requestAnimationFrame(poll);
        } catch (err) {
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
        };

        recognition.onaudiostart = () => {
        };

        recognition.onsoundstart = () => {
        };

        recognition.onspeechstart = () => {
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
            }

            if (interimTranscript) {
                setInterimText(interimTranscript);
            }
        };

        recognition.onerror = (event) => {
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                setMicError('Microphone blocked! Click the lock icon in address bar → Allow microphone.');
                wantListeningRef.current = false;
                setIsListening(false);
                stopMicMonitor();
            } else if (event.error === 'no-speech') {
                // Chrome fires this after ~5s of silence — auto-restart via onend
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
            recognitionRef.current = null;
            if (wantListeningRef.current) {
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
        } catch (err) {
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
            id: crypto.randomUUID(),
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
                id: crypto.randomUUID(),
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
                id: crypto.randomUUID(),
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

    const handleClear = () => {
        if (confirmingClear) {
            setMessages([]);
            setConfirmingClear(false);
            // Also clear from DB for authenticated users
            if (isAuthenticated && sessionId) {
                clearChatHistoryApi(sessionId).catch(() => {});
            }
        } else {
            setConfirmingClear(true);
            // Auto-cancel after 3 seconds
            setTimeout(() => setConfirmingClear(false), 3000);
        }
    };

    const detectHindi = (text) => {
        const hindiRegex = /[\u0900-\u097F]/;
        return hindiRegex.test(text);
    };

    const getMicBarColor = () => {
        if (micLevel > 40) return '#16a34a';
        if (micLevel > 15) return '#d97706';
        return '#dc2626';
    };

    return (
        <div className="chat-container">
            {/* Controls bar */}
            <div className="chat-controls">
                <div className="language-selector">
                    <label className="language-selector-label">
                        <Icons.Globe size={11} />
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
                    <button className={`btn btn-ghost btn-sm ${confirmingClear ? 'btn-danger' : ''}`} onClick={handleClear}>
                        <Icons.Delete size={13} />
                        {confirmingClear ? 'Confirm Clear?' : 'Clear'}
                    </button>
                )}
            </div>

            {/* Messages */}
            <div className="chat-messages" role="log" aria-live="polite" aria-label="Chat messages">
                {historyLoading ? (
                    <div className="chat-empty-state">
                        <Icons.Loading size={24} className="animate-spin" />
                        <p className="chat-empty-text">Loading chat history…</p>
                    </div>
                ) : messages.length === 0 ? (
                    <div className="chat-empty-state">
                        <Icons.Chat size={28} className="chat-empty-icon" />
                        <p className="chat-empty-text">Ask anything about this discourse</p>
                        <p className="chat-empty-hint">
                            {micSupported ? 'Type or use the microphone' : 'Type your question below'}
                        </p>
                        <div className="chat-suggestions">
                            <button className="chat-suggestion-chip" onClick={() => setInput('इसका सारांश बताइए')}>
                                इसका सारांश बताइए
                            </button>
                            <button className="chat-suggestion-chip" onClick={() => setInput('What is the main teaching?')}>
                                Main teaching?
                            </button>
                            <button className="chat-suggestion-chip" onClick={() => setInput('Key takeaways?')}>
                                Key takeaways?
                            </button>
                        </div>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={`chat-message ${msg.role} ${detectHindi(msg.content) ? 'hindi' : ''}`}
                        >
                            <p style={{ fontFamily: detectHindi(msg.content) ? 'var(--font-hindi)' : undefined }}>
                                {msg.content}
                            </p>

                            {msg.role === 'assistant' && !msg.isError && (
                                <div className="chat-msg-tts">
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
                        <div className="chat-loading">
                            <Icons.Loading size={18} className="animate-spin" />
                            <span>Thinking...</span>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Mic error */}
            {micError && (
                <div className="chat-mic-error">{micError}</div>
            )}

            {/* Listening indicator */}
            {/* Input */}
            <div className="chat-input-container">
                {micSupported ? (
                    <button
                        className={`voice-btn ${isListening ? 'listening' : ''}`}
                        onClick={toggleListening}
                        title={isListening ? 'Click to stop listening' : 'Click to speak'}
                        disabled={isLoading}
                        type="button"
                    >
                        <Icons.Mic size={17} />
                    </button>
                ) : (
                    <button
                        className="voice-btn"
                        onClick={() => {
                            setMicError('Speech recognition requires Google Chrome or Microsoft Edge browser.');
                            setTimeout(() => setMicError(null), 5000);
                        }}
                        title="Speech recognition not supported in this browser"
                        type="button"
                        disabled
                    >
                        <Icons.Mic size={17} />
                    </button>
                )}
                <input
                    ref={inputRef}
                    className="chat-input"
                    type="text"
                    aria-label="Ask a question about this discourse"
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
                    {isLoading ? <Icons.Loading size={17} className="animate-spin" /> : <Icons.Send size={17} />}
                </button>
            </div>
        </div>
    );
}

export default Chat;

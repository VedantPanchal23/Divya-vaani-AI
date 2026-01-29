import { useState, useEffect, useRef } from 'react';
import { sendMessage } from '../api';
import TextToSpeech from './TextToSpeech';
import { Icons } from './Icons';
import { FiMic, FiMicOff } from 'react-icons/fi';

function Chat({ sessionId, onNewMessage }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [outputLanguage, setOutputLanguage] = useState('auto');
    const [isListening, setIsListening] = useState(false);
    const [speechSupported, setSpeechSupported] = useState(false);
    const messagesEndRef = useRef(null);
    const recognitionRef = useRef(null);

    // Check if Speech Recognition is supported
    useEffect(() => {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            setSpeechSupported(true);
            recognitionRef.current = new SpeechRecognition();
            recognitionRef.current.continuous = false;
            recognitionRef.current.interimResults = true;
            recognitionRef.current.lang = 'hi-IN'; // Support Hindi by default

            recognitionRef.current.onresult = (event) => {
                const transcript = Array.from(event.results)
                    .map(result => result[0].transcript)
                    .join('');
                setInput(transcript);
            };

            recognitionRef.current.onend = () => {
                setIsListening(false);
            };

            recognitionRef.current.onerror = (event) => {
                console.error('Speech recognition error:', event.error);
                setIsListening(false);
            };
        }

        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
            }
        };
    }, []);

    // Update recognition language based on output preference
    useEffect(() => {
        if (recognitionRef.current) {
            recognitionRef.current.lang = outputLanguage === 'hi' ? 'hi-IN' :
                outputLanguage === 'en' ? 'en-US' : 'hi-IN';
        }
    }, [outputLanguage]);

    // Load chat history
    useEffect(() => {
        if (sessionId) {
            loadHistory();
        }
    }, [sessionId]);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const loadHistory = async () => {
        // History is now managed locally, backend doesn't persist chat
        setMessages([]);
    };

    const toggleListening = () => {
        if (!recognitionRef.current) return;

        if (isListening) {
            recognitionRef.current.stop();
            setIsListening(false);
        } else {
            setInput('');
            recognitionRef.current.start();
            setIsListening(true);
        }
    };

    const handleSend = async () => {
        if (!input.trim() || isLoading) return;

        // Stop listening if active
        if (isListening && recognitionRef.current) {
            recognitionRef.current.stop();
            setIsListening(false);
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
            // Use new API: sendMessage(question, transcriptId, language)
            const lang = outputLanguage === 'auto' ? 'hi' : outputLanguage;
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
                            {speechSupported ? 'Type or use 🎙️ to speak your question' : 'Type your question below'}
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

                            {/* TTS for assistant messages */}
                            {msg.role === 'assistant' && !msg.isError && (
                                <div style={{ marginTop: 'var(--spacing-sm)' }}>
                                    <TextToSpeech
                                        text={msg.content}
                                        lang={detectHindi(msg.content) ? 'hi-IN' : 'en-US'}
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

            {/* Input with Voice */}
            <div className="chat-input-container">
                {speechSupported && (
                    <button
                        className={`btn btn-icon voice-btn ${isListening ? 'listening' : ''}`}
                        onClick={toggleListening}
                        title={isListening ? 'Stop listening' : 'Speak your question'}
                        disabled={isLoading}
                    >
                        {isListening ? <FiMicOff size={18} /> : <FiMic size={18} />}
                    </button>
                )}
                <input
                    className="chat-input"
                    type="text"
                    placeholder={isListening ? 'Listening... 🎙️' : (outputLanguage === 'hi' ? 'हिंदी में पूछें...' : 'Ask in Hindi or English...')}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isLoading}
                />
                <button
                    className="btn btn-primary btn-icon"
                    onClick={handleSend}
                    disabled={!input.trim() || isLoading}
                >
                    <Icons.Send size={18} />
                </button>
            </div>
        </div>
    );
}

export default Chat;

import { useState, useEffect, useRef } from 'react';
import { sendMessage } from '../api';
import { Icons } from './Icons';
import { FiMic, FiMicOff } from 'react-icons/fi';

// Custom confirmation dialog (replaces browser confirm())
function ConfirmDialog({ message, onConfirm, onCancel }) {
    return (
        <div className="confirm-overlay" onClick={onCancel}>
            <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
                <p>{message}</p>
                <div className="confirm-actions">
                    <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
                    <button className="btn btn-primary btn-sm" onClick={onConfirm}>Clear</button>
                </div>
            </div>
        </div>
    );
}

function Chat({ sessionId, onNewMessage }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [outputLanguage, setOutputLanguage] = useState('auto');
    const [isListening, setIsListening] = useState(false);
    const [speechSupported, setSpeechSupported] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
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

    const handleClear = () => {
        setShowConfirm(true);
    };

    const confirmClear = () => {
        setMessages([]);
        setShowConfirm(false);
    };

    const detectHindi = (text) => {
        const hindiRegex = /[\u0900-\u097F]/;
        return hindiRegex.test(text);
    };

    return (
        <div className="chat-container">
            {/* Language Selector & Clear Button */}
            <div className="chat-toolbar">
                <div className="language-selector">
                    <label className="language-label">
                        <Icons.Globe size={12} />
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
                    <div className="chat-empty-state">
                        <Icons.Chat size={32} className="chat-empty-icon" />
                        <p className="chat-empty-text">Ask anything about the speech</p>
                        <p className="chat-empty-hint">
                            {speechSupported ? 'Type or use 🎙️ to speak your question' : 'Type your question below'}
                        </p>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <div
                            key={msg.id}
                            className={`chat-message ${msg.role} ${detectHindi(msg.content) ? 'hindi' : ''}`}
                        >
                            <p className={detectHindi(msg.content) ? 'hindi-text' : ''}>
                                {msg.content}
                            </p>

                            {msg.quotes && msg.quotes.length > 0 && (
                                <div className="chat-quotes">
                                    <strong className="chat-quotes-label">
                                        <Icons.BookOpen size={14} />
                                        From the speech:
                                    </strong>
                                    {msg.quotes.map((quote, i) => (
                                        <p key={i} className="chat-quote">"{quote}"</p>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))
                )}

                {isLoading && (
                    <div className="chat-message assistant">
                        <div className="loading-text">
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

            {/* Custom Confirm Dialog */}
            {showConfirm && (
                <ConfirmDialog
                    message="Clear all chat history?"
                    onConfirm={confirmClear}
                    onCancel={() => setShowConfirm(false)}
                />
            )}
        </div>
    );
}

export default Chat;

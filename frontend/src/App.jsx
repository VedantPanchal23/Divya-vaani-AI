import { useState, useEffect, useRef, useCallback } from 'react';
import Upload from './components/Upload';
import SessionList from './components/SessionList';
import TranscriptViewer from './components/TranscriptViewer';
import MediaPlayer from './components/MediaPlayer';
import Summary from './components/Summary';
import Chat from './components/Chat';
import { Icons } from './components/Icons';
import { getTranscripts, getTranscript } from './api';

function App() {
    const [sessions, setSessions] = useState([]);
    const [activeSession, setActiveSession] = useState(null);
    const [sessionData, setSessionData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [theme, setTheme] = useState(() => {
        return localStorage.getItem('theme') || 'light';
    });
    const [isThemeTransitioning, setIsThemeTransitioning] = useState(false);
    const mediaRef = useRef(null);
    const activeSessionRef = useRef(null);  // Ref to track active session for polling
    const pollRef = useRef(null);  // Ref to track and cancel active polls

    // Apply theme on mount and change with animation
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    // Keep activeSessionRef in sync with activeSession state
    useEffect(() => {
        activeSessionRef.current = activeSession;
    }, [activeSession]);

    const toggleTheme = () => {
        setIsThemeTransitioning(true);
        setTimeout(() => {
            setTheme(prev => prev === 'light' ? 'dark' : 'light');
        }, 150);
        setTimeout(() => {
            setIsThemeTransitioning(false);
        }, 500);
    };

    // Fetch sessions on mount
    useEffect(() => {
        fetchSessions();
    }, []);

    const fetchSessions = async () => {
        try {
            const data = await getTranscripts();
            // Transform to expected format
            const sessions = Array.isArray(data) ? data : (data.sessions || []);
            setSessions(sessions.map(s => ({
                id: s.id,
                filename: s.filename,
                title: s.title,
                status: 'complete',
                created_at: s.created_at
            })));
        } catch (error) {
            console.error('Failed to fetch sessions:', error);
        }
    };

    // Fetch session data when active session changes (but not if we're polling)
    useEffect(() => {
        if (activeSession && !pollRef.current) {
            fetchSessionData(activeSession);
        }
    }, [activeSession]);

    const fetchSessionData = async (sessionId) => {
        setLoading(true);
        try {
            // Fetch both Hindi and English versions
            const [dataHi, dataEn] = await Promise.all([
                getTranscript(sessionId, 'hi'),
                getTranscript(sessionId, 'en')
            ]);

            // Determine status - 'complete' or 'ready' means processing is done
            const isComplete = dataHi.status === 'complete' || dataHi.status === 'ready' || 
                              (dataHi.full_text && dataHi.full_text.length > 0);

            // Transform to expected format with both languages
            setSessionData({
                ...dataHi,
                status: isComplete ? 'complete' : dataHi.status,
                transcript: dataHi.full_text,
                transcript_segments: dataHi.chunks,
                summary: {
                    hindi: dataHi.summary || '',
                    english: dataEn.summary || ''
                },
                explanation: {
                    hindi: dataHi.explanation || '',
                    english: dataEn.explanation || ''
                },
                summary_audio: {
                    hindi: dataHi.summary_audio || '',
                    english: dataEn.summary_audio || ''
                },
                explanation_audio: {
                    hindi: dataHi.explanation_audio || '',
                    english: dataEn.explanation_audio || ''
                }
            });
        } catch (error) {
            console.error('Failed to fetch session data:', error);
        } finally {
            setLoading(false);
        }
    };

    // Poll for processing status - auto-refresh when complete
    const pollStatus = useCallback((sessionId) => {
        // Cancel any existing poll for this session
        if (pollRef.current) {
            pollRef.current.cancelled = true;
        }
        
        const pollContext = { cancelled: false };
        pollRef.current = pollContext;
        
        const poll = async () => {
            if (pollContext.cancelled) return;
            
            try {
                const status = await getTranscript(sessionId);
                
                if (pollContext.cancelled) return;

                // Determine if processing is complete
                // Backend returns status: "processing" with step field, or status: "complete"
                const isComplete = status.status === 'complete' || status.status === 'ready' ||
                    (status.full_text && status.summary && status.status !== 'processing');
                const isError = status.status === 'error' || status.step === 'failed';
                const isProcessing = !isComplete && !isError;

                // Update session status in list
                const sessionStatus = isComplete ? 'complete' : isError ? 'error' : 'processing';
                
                setSessions(prev => prev.map(s =>
                    s.id === sessionId ? { 
                        ...s, 
                        status: sessionStatus,
                        step: status.step,
                        progress: status.progress,
                        message: status.message
                    } : s
                ));

                // Update session data in real-time during processing (use ref for current value)
                if (activeSessionRef.current === sessionId) {
                    if (isProcessing) {
                        // Update progress during processing
                        setSessionData(prev => ({
                            ...prev,
                            status: sessionStatus,
                            step: status.step,
                            progress: status.progress,
                            message: status.message,
                            ...(status.full_text && { transcript: status.full_text }),
                            ...(status.chunks && { transcript_segments: status.chunks })
                        }));
                    }
                }

                // If still processing, continue polling (slower interval)
                if (isProcessing && !pollContext.cancelled) {
                    setTimeout(poll, 3000);  // 3 seconds instead of 2
                } else if (isComplete || isError) {
                    // Processing complete or error - fetch full session data ONCE
                    console.log('Processing complete! Fetching full session data...');
                    
                    // Clear the poll reference since we're done
                    if (pollRef.current === pollContext) {
                        pollRef.current = null;
                    }
                    
                    // Always fetch the complete data when done
                    if (activeSessionRef.current === sessionId && !pollContext.cancelled) {
                        // Fetch both Hindi and English versions
                        try {
                            const [dataHi, dataEn] = await Promise.all([
                                getTranscript(sessionId, 'hi'),
                                getTranscript(sessionId, 'en')
                            ]);

                            const finalStatus = dataHi.status === 'complete' || dataHi.full_text ? 'complete' : dataHi.status;

                            setSessionData({
                                ...dataHi,
                                status: finalStatus,
                                transcript: dataHi.full_text,
                                transcript_segments: dataHi.chunks,
                                summary: {
                                    hindi: dataHi.summary || '',
                                    english: dataEn.summary || ''
                                },
                                explanation: {
                                    hindi: dataHi.explanation || '',
                                    english: dataEn.explanation || ''
                                },
                                summary_audio: {
                                    hindi: dataHi.summary_audio || '',
                                    english: dataEn.summary_audio || ''
                                },
                                explanation_audio: {
                                    hindi: dataHi.explanation_audio || '',
                                    english: dataEn.explanation_audio || ''
                                }
                            });
                            console.log('Session data updated with complete results!');
                        } catch (error) {
                            console.error('Failed to fetch complete session data:', error);
                        }
                    }
                    fetchSessions();
                }
            } catch (error) {
                console.error('Polling error:', error);
                // Retry on error (but don't spam)
                if (!pollContext.cancelled) {
                    setTimeout(poll, 5000);  // 5 seconds on error
                }
            }
        };
        
        poll();
        
        // Return cleanup function
        return () => {
            pollContext.cancelled = true;
            if (pollRef.current === pollContext) {
                pollRef.current = null;
            }
        };
    }, []);  // No dependencies - uses ref for activeSession

    const handleUploadSuccess = (result) => {
        const newSession = {
            id: result.file_id,
            filename: result.filename,
            status: 'processing',
            step: 'transcribing',
            progress: 0,
            created_at: new Date().toISOString()
        };
        
        setSessions(prev => [newSession, ...prev]);
        setActiveSession(result.file_id);
        
        // Initialize session data to show processing UI immediately
        setSessionData({
            id: result.file_id,
            filename: result.filename,
            status: 'processing',
            step: 'transcribing',
            progress: 0,
            message: 'Starting transcription...'
        });
        
        pollStatus(result.file_id);
    };

    const handleSeek = (time) => {
        if (mediaRef.current) {
            mediaRef.current.currentTime = time;
            mediaRef.current.play();
        }
    };

    const handleTimeUpdate = (time) => {
        setCurrentTime(time);
    };

    // Get processing step info
    const getProcessingSteps = (status) => {
        const steps = [
            { key: 'transcribing', label: 'Transcribing', labelHi: 'लिप्यंतरण', icon: <Icons.Mic size={16} /> },
            { key: 'summarizing', label: 'Summarizing', labelHi: 'सारांश', icon: <Icons.Summary size={16} /> },
            { key: 'explaining', label: 'Explaining', labelHi: 'व्याख्या', icon: <Icons.Explanation size={16} /> },
            { key: 'embedding', label: 'Embedding', labelHi: 'एम्बेडिंग', icon: <Icons.AI size={16} /> },
        ];

        const currentIndex = steps.findIndex(s => s.key === status);
        return steps.map((step, i) => ({
            ...step,
            done: i < currentIndex,
            active: i === currentIndex,
        }));
    };

    return (
        <div className={`app ${isThemeTransitioning ? 'theme-transitioning' : ''}`}>
            {/* Header */}
            <header className="header">
                <div className="header-logo">
                    <span className="header-logo-icon">
                        <Icons.Spiritual size={28} />
                    </span>
                    <span className="header-logo-text">Spiritual Teachings AI</span>
                </div>
                <nav className="header-nav">
                    <span className="header-badge">
                        <Icons.Globe size={14} />
                        Hindi + English
                    </span>
                    <span className="header-badge">
                        <Icons.AI size={14} />
                        AI-Powered
                    </span>
                    <button
                        className={`theme-toggle ${isThemeTransitioning ? 'transitioning' : ''}`}
                        onClick={toggleTheme}
                        title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
                    >
                        <span className="theme-toggle-icon">
                            {theme === 'light' ? <Icons.Moon size={20} /> : <Icons.Sun size={20} />}
                        </span>
                    </button>
                </nav>
            </header>

            {/* Main Layout */}
            <main className="main-layout">
                {/* Left Sidebar - Sessions */}
                <aside>
                    <div className="card fade-in" style={{ marginBottom: 'var(--spacing-lg)' }}>
                        <Upload onSuccess={handleUploadSuccess} />
                    </div>

                    <div className="card fade-in">
                        <div className="card-header">
                            <h3 className="card-title">
                                <Icons.Sessions size={18} className="card-title-icon" />
                                Sessions
                            </h3>
                        </div>
                        <SessionList
                            sessions={sessions}
                            activeSession={activeSession}
                            onSelect={setActiveSession}
                            onRefresh={fetchSessions}
                        />
                    </div>
                </aside>

                {/* Center - Content */}
                <section>
                    {!activeSession ? (
                        <div className="card fade-in">
                            <div className="empty-state">
                                <span className="empty-state-icon">
                                    <Icons.Mic size={48} />
                                </span>
                                <p className="empty-state-text">
                                    Upload a spiritual speech to get started
                                </p>
                                <p style={{ color: 'var(--color-text-muted)', marginTop: '0.5rem' }}>
                                    Supports MP3, MP4, WAV, and more
                                </p>
                            </div>
                        </div>
                    ) : loading ? (
                        <div className="card">
                            <div className="empty-state">
                                <Icons.Loading size={40} className="animate-spin" />
                                <p className="empty-state-text" style={{ marginTop: '1rem' }}>
                                    Loading session...
                                </p>
                            </div>
                        </div>
                    ) : sessionData ? (
                        <>
                            {/* Media Player */}
                            {sessionData.media_url && (
                                <div className="card fade-in" style={{ marginBottom: 'var(--spacing-lg)' }}>
                                    <MediaPlayer
                                        ref={mediaRef}
                                        url={sessionData.media_url}
                                        type={sessionData.file_type}
                                        onTimeUpdate={handleTimeUpdate}
                                    />
                                </div>
                            )}

                            {/* Processing Status with Steps */}
                            {sessionData.status === 'processing' && sessionData.status !== 'complete' && sessionData.status !== 'error' && (
                                <div className="card fade-in" style={{ marginBottom: 'var(--spacing-lg)' }}>
                                    <div className="card-header">
                                        <h3 className="card-title">
                                            <Icons.Processing size={18} className="card-title-icon animate-spin" />
                                            Processing
                                        </h3>
                                        <div className="audio-waveform">
                                            <div className="audio-bar"></div>
                                            <div className="audio-bar"></div>
                                            <div className="audio-bar"></div>
                                            <div className="audio-bar"></div>
                                            <div className="audio-bar"></div>
                                        </div>
                                    </div>
                                    {sessionData.message && (
                                        <p style={{ color: 'var(--color-text-muted)', marginBottom: '1rem', fontSize: '0.9rem' }}>
                                            {sessionData.message}
                                        </p>
                                    )}
                                    <div className="processing-steps">
                                        {getProcessingSteps(sessionData.step || 'transcribing').map((step) => (
                                            <div
                                                key={step.key}
                                                className={`processing-step ${step.active ? 'active' : ''} ${step.done ? 'done' : ''}`}
                                            >
                                                <span className="processing-step-icon">
                                                    {step.done ? <Icons.Done size={16} /> : step.active ? <Icons.Loading size={16} className="animate-spin" /> : step.icon}
                                                </span>
                                                <span>{step.label}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Error State */}
                            {sessionData.status === 'error' && (
                                <div className="card fade-in" style={{ marginBottom: 'var(--spacing-lg)', borderLeft: '4px solid var(--color-error)' }}>
                                    <div className="card-header">
                                        <h3 className="card-title" style={{ color: 'var(--color-error)' }}>
                                            <Icons.Error size={18} className="card-title-icon" />
                                            Error
                                        </h3>
                                    </div>
                                    <p style={{ color: 'var(--color-error)' }}>
                                        {sessionData.error_message || 'An error occurred during processing'}
                                    </p>
                                </div>
                            )}

                            {/* Summary & Explanation */}
                            {(sessionData.summary?.english || sessionData.summary?.hindi) && (
                                <div className="card fade-in" style={{ marginBottom: 'var(--spacing-lg)' }}>
                                    <div className="card-header">
                                        <h3 className="card-title">
                                            <Icons.Summary size={18} className="card-title-icon" />
                                            Summary & Explanation
                                        </h3>
                                    </div>
                                    <Summary
                                        summary={sessionData.summary}
                                        explanation={sessionData.explanation}
                                    />
                                </div>
                            )}

                            {/* Transcript */}
                            {sessionData.transcript && (
                                <div className="card fade-in">
                                    <div className="card-header">
                                        <h3 className="card-title">
                                            <Icons.Transcript size={18} className="card-title-icon" />
                                            Transcript
                                        </h3>
                                        <span className="status-badge status-ready">
                                            {sessionData.detected_language || 'auto'}
                                        </span>
                                    </div>
                                    <TranscriptViewer
                                        transcript={sessionData.transcript}
                                        segments={sessionData.transcript_segments}
                                        currentTime={currentTime}
                                        onSeek={handleSeek}
                                    />
                                </div>
                            )}
                        </>
                    ) : null}
                </section>

                {/* Right Sidebar - Chat */}
                <aside>
                    <div className="card fade-in" style={{ height: '100%' }}>
                        <div className="card-header">
                            <h3 className="card-title">
                                <Icons.Chat size={18} className="card-title-icon" />
                                Ask Questions
                            </h3>
                        </div>
                        {sessionData?.status === 'complete' ? (
                            <Chat
                                sessionId={activeSession}
                                onNewMessage={() => { }}
                            />
                        ) : (
                            <div className="empty-state">
                                <span className="empty-state-icon">
                                    <Icons.Question size={48} />
                                </span>
                                <p className="empty-state-text">
                                    {!activeSession
                                        ? 'Select a session to ask questions'
                                        : 'Wait for processing to complete'
                                    }
                                </p>
                            </div>
                        )}
                    </div>
                </aside>
            </main>
        </div>
    );
}

export default App;

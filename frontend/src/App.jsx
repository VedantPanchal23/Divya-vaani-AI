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

    // Apply theme on mount and change with animation
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

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

    // Fetch session data when active session changes
    useEffect(() => {
        if (activeSession) {
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

            // Transform to expected format with both languages
            setSessionData({
                ...dataHi,
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

    // Poll for processing status
    const pollStatus = useCallback(async (sessionId) => {
        const poll = async () => {
            try {
                const status = await getTranscript(sessionId);

                // Update session in list
                const sessionStatus = status.status === 'complete' ? 'complete' :
                    status.status === 'error' ? 'error' : 'processing';

                setSessions(prev => prev.map(s =>
                    s.id === sessionId ? { ...s, status: sessionStatus } : s
                ));

                // If still processing, continue polling
                if (status.status === 'processing') {
                    setTimeout(poll, 2000);
                } else {
                    // Refresh session data when done
                    if (activeSession === sessionId) {
                        fetchSessionData(sessionId);
                    }
                    fetchSessions();
                }
            } catch (error) {
                console.error('Polling error:', error);
                // Retry on error
                setTimeout(poll, 3000);
            }
        };
        poll();
    }, [activeSession]);

    const handleUploadSuccess = (result) => {
        setSessions(prev => [{
            id: result.file_id,
            filename: result.filename,
            status: 'processing',
            created_at: new Date().toISOString()
        }, ...prev]);

        setActiveSession(result.file_id);
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
                            {sessionData.status !== 'ready' && sessionData.status !== 'error' && (
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
                                    <div className="processing-steps">
                                        {getProcessingSteps(sessionData.status).map((step) => (
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

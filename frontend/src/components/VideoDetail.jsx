import { useState, useEffect, useRef } from 'react';
import Chat from './Chat';
import { Icons } from './Icons';
import { getVideo, generateVideoSummary } from '../api';
import TextToSpeech from './TextToSpeech';

// Simple markdown-like text formatter (safe - no dangerouslySetInnerHTML)
function formatText(text) {
    if (!text) return null;
    
    // Split by lines and process
    const lines = text.split('\n');
    const elements = [];
    let listItems = [];
    
    // Helper: render text with bold markers safely
    function renderBoldText(str, keyPrefix) {
        const parts = str.split(/\*\*(.+?)\*\*/g);
        return parts.map((part, i) =>
            i % 2 === 1
                ? <strong key={`${keyPrefix}-b${i}`}>{part}</strong>
                : <span key={`${keyPrefix}-s${i}`}>{part}</span>
        );
    }
    
    lines.forEach((line, idx) => {
        const trimmed = line.trim();
        
        // Check for bullet points
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
            const content = trimmed.slice(2);
            listItems.push(
                <li key={`li-${idx}`}>{renderBoldText(content, `li-${idx}`)}</li>
            );
        } else {
            // Flush list items if any
            if (listItems.length > 0) {
                elements.push(<ul key={`ul-${idx}`}>{[...listItems]}</ul>);
                listItems = [];
            }
            
            // Process bold text and add as paragraph
            if (trimmed) {
                elements.push(
                    <p key={`p-${idx}`}>{renderBoldText(trimmed, `p-${idx}`)}</p>
                );
            }
        }
    });
    
    // Flush remaining list items
    if (listItems.length > 0) {
        elements.push(<ul key="ul-final">{[...listItems]}</ul>);
    }
    
    return elements;
}

function VideoDetail({ videoId, onBack }) {
    const [video, setVideo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [language, setLanguage] = useState('hindi'); // hindi or english
    const [generatingSummary, setGeneratingSummary] = useState(false);
    const refreshTimersRef = useRef([]);

    // Cleanup timers on unmount
    useEffect(() => {
        return () => {
            refreshTimersRef.current.forEach(clearTimeout);
        };
    }, []);

    const loadVideo = async () => {
        setLoading(true);
        setError(null);
        
        try {
            const [dataHi, dataEn] = await Promise.all([
                getVideo(videoId, 'hi'),
                getVideo(videoId, 'en')
            ]);

            setVideo({
                ...dataHi,
                title_en: dataEn.title,
                summary: {
                    hindi: dataHi.summary_hi || dataHi.summary || '',
                    english: dataEn.summary_en || dataEn.summary || ''
                },
                explanation: {
                    hindi: dataHi.explanation_hi || dataHi.explanation || '',
                    english: dataEn.explanation_en || dataEn.explanation || ''
                }
            });
        } catch (err) {
            setError(err.message || 'Failed to load video');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (videoId) {
            loadVideo();
        }
    }, [videoId]);

    const formatDuration = (seconds) => {
        if (!seconds) return '--:--';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (mins >= 60) {
            const hrs = Math.floor(mins / 60);
            const remainMins = mins % 60;
            return `${hrs}h ${remainMins}m`;
        }
        return `${mins}m ${secs}s`;
    };

    const currentSummary = language === 'english' ? video?.summary?.english : video?.summary?.hindi;
    const currentExplanation = language === 'english' ? video?.explanation?.english : video?.explanation?.hindi;

    if (loading) {
        return (
            <div className="video-detail-single">
                <div className="video-detail-loading">
                    <Icons.Loading size={48} className="animate-spin" />
                    <p>Loading content...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="video-detail-single">
                <div className="video-detail-error">
                    <Icons.Error size={48} />
                    <h3>Failed to load</h3>
                    <p>{error}</p>
                    <button className="btn btn-primary" onClick={loadVideo}>
                        Try Again
                    </button>
                </div>
            </div>
        );
    }

    if (!video) return null;

    return (
        <div className="video-detail-single">
            {/* Compact Header */}
            <div className="vd-header">
                <button className="btn btn-ghost vd-back" onClick={onBack}>
                    <Icons.Back size={18} />
                    Back
                </button>
                
                <div className="vd-title-area">
                    <h1 className="vd-title">{video.title_hi || video.title}</h1>
                    <div className="vd-meta">
                        <span><Icons.Spiritual size={14} /> {video.speaker || 'Maharaj Ji'}</span>
                        <span><Icons.Clock size={14} /> {formatDuration(video.duration)}</span>
                        <span className="vd-category">{video.category || 'Pravachan'}</span>
                    </div>
                </div>

                {/* Language Toggle */}
                <div className="vd-lang-toggle">
                    <button 
                        className={`vd-lang-btn ${language === 'english' ? 'active' : ''}`}
                        onClick={() => setLanguage('english')}
                    >
                        EN
                    </button>
                    <button 
                        className={`vd-lang-btn ${language === 'hindi' ? 'active' : ''}`}
                        onClick={() => setLanguage('hindi')}
                    >
                        हिं
                    </button>
                </div>
            </div>

            {/* Main Content Grid */}
            <div className="vd-grid">
                {/* Left Column: Video + Summary + Explanation */}
                <div className="vd-left">
                    {/* Video Player */}
                    <div className="vd-video-section">
                        <div className="vd-video-placeholder">
                            {video.video_url ? (
                                <video 
                                    controls 
                                    src={video.video_url}
                                    className="vd-video-player"
                                />
                            ) : (
                                <div className="vd-no-video">
                                    <Icons.Play size={48} />
                                    <p>Audio Discourse</p>
                                    <span>Video not available</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Summary Section */}
                    <div className="vd-section vd-summary-section">
                        <div className="vd-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h3><Icons.Summary size={18} /> Summary</h3>
                            {currentSummary && (
                                <TextToSpeech 
                                    text={currentSummary} 
                                    lang={language === 'hindi' ? 'hi' : 'en'}
                                />
                            )}
                        </div>
                        <div className={`vd-section-content ${language === 'hindi' ? 'hindi-text' : ''}`}>
                            {currentSummary ? (
                                <div>{formatText(currentSummary)}</div>
                            ) : (
                                <div className="vd-empty">
                                    <p>Summary not available</p>
                                    <button 
                                        className="btn btn-primary btn-sm"
                                        onClick={async () => {
                                            setGeneratingSummary(true);
                                            try {
                                                await generateVideoSummary(videoId);
                                                refreshTimersRef.current.push(
                                                    setTimeout(() => loadVideo(), 5000),
                                                    setTimeout(() => loadVideo(), 15000)
                                                );
                                            } catch (e) {
                                                console.error('Generate failed:', e);
                                                alert(e.message || 'Failed to generate summary. Admin access may be required.');
                                            }
                                            setGeneratingSummary(false);
                                        }}
                                        disabled={generatingSummary}
                                    >
                                        {generatingSummary ? (
                                            <><Icons.Loading size={14} className="animate-spin" /> Generating...</>
                                        ) : (
                                            <><Icons.Sparkles size={14} /> Generate</>
                                        )}
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Explanation Section */}
                    <div className="vd-section vd-explanation-section">
                        <div className="vd-section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <h3><Icons.Explanation size={18} /> Explanation</h3>
                            {currentExplanation && (
                                <TextToSpeech 
                                    text={currentExplanation} 
                                    lang={language === 'hindi' ? 'hi' : 'en'}
                                />
                            )}
                        </div>
                        <div className={`vd-section-content ${language === 'hindi' ? 'hindi-text' : ''}`}>
                            {currentExplanation ? (
                                <div>{formatText(currentExplanation)}</div>
                            ) : (
                                <div className="vd-empty">
                                    <p>Explanation not available</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right Column: Q&A Chat */}
                <div className="vd-right">
                    <div className="vd-chat-section">
                        <div className="vd-chat-header">
                            <h3><Icons.Chat size={18} /> Ask Questions</h3>
                        </div>
                        <div className="vd-chat-container">
                            <Chat
                                sessionId={videoId}
                                onNewMessage={() => {}}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default VideoDetail;

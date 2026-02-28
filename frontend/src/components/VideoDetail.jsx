import { useState, useEffect } from 'react';
import Chat from './Chat';
import { Icons } from './Icons';
import { getVideo, generateVideoSummary } from '../api';

/**
 * Extract YouTube video ID from various URL formats.
 * Supports: youtube.com/watch?v=, youtu.be/, youtube.com/embed/, youtube.com/shorts/
 * Returns null if not a YouTube URL.
 */
function getYouTubeId(url) {
    if (!url) return null;
    const patterns = [
        /(?:youtube\.com\/watch\?v=|youtube\.com\/embed\/|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/,
        /^([a-zA-Z0-9_-]{11})$/  // bare video ID
    ];
    for (const pattern of patterns) {
        const match = url.match(pattern);
        if (match) return match[1];
    }
    return null;
}

/**
 * YouTube Embed Player - responsive iframe with privacy-enhanced mode
 */
function YouTubePlayer({ videoUrl }) {
    const [embedError, setEmbedError] = useState(false);
    const ytId = getYouTubeId(videoUrl);

    if (!ytId) {
        // Non-YouTube video URL - use HTML5 player
        return (
            <div className="yt-player-wrap">
                <video controls src={videoUrl} className="yt-player-video" />
            </div>
        );
    }

    const watchUrl = `https://www.youtube.com/watch?v=${ytId}`;

    return (
        <div className="yt-player-wrap">
            {!embedError ? (
                <iframe
                    className="yt-player-iframe"
                    src={`https://www.youtube.com/embed/${ytId}?rel=0&modestbranding=1&origin=${window.location.origin}`}
                    title="Spiritual Discourse Video"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    referrerPolicy="strict-origin-when-cross-origin"
                    allowFullScreen
                    loading="lazy"
                    onError={() => setEmbedError(true)}
                />
            ) : (
                <div className="yt-player-fallback">
                    <img
                        src={`https://img.youtube.com/vi/${ytId}/hqdefault.jpg`}
                        alt="Video thumbnail"
                        className="yt-player-fallback-thumb"
                    />
                    <a href={watchUrl} target="_blank" rel="noopener noreferrer" className="yt-player-fallback-btn">
                        ▶ Watch on YouTube
                    </a>
                </div>
            )}
            <a
                href={watchUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="yt-player-external-link"
            >
                Watch on YouTube ↗
            </a>
        </div>
    );
}

// Simple markdown-like text formatter (XSS-safe)
function formatText(text) {
    if (!text) return null;

    const lines = text.split('\n');
    const elements = [];
    let listItems = [];

    const renderWithBold = (content, key) => {
        const parts = content.split(/\*\*(.+?)\*\*/g);
        return parts.map((part, i) =>
            i % 2 === 1 ? <strong key={`${key}-bold-${i}`}>{part}</strong> : part
        );
    };

    lines.forEach((line, idx) => {
        const trimmed = line.trim();

        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
            const content = trimmed.slice(2);
            listItems.push(
                <li key={`li-${idx}`}>{renderWithBold(content, `li-${idx}`)}</li>
            );
        } else {
            if (listItems.length > 0) {
                elements.push(<ul key={`ul-${idx}`}>{listItems}</ul>);
                listItems = [];
            }

            if (trimmed) {
                elements.push(
                    <p key={`p-${idx}`}>{renderWithBold(trimmed, `p-${idx}`)}</p>
                );
            }
        }
    });

    if (listItems.length > 0) {
        elements.push(<ul key="ul-final">{listItems}</ul>);
    }

    return elements;
}

// Transcript Viewer (flat inside tab, always open)
function TranscriptViewer({ chunks, language }) {
    const [filter, setFilter] = useState('');

    if (!chunks || chunks.length === 0) {
        return (
            <div className="vd-empty">
                <Icons.Transcript size={32} />
                <p>Transcript not available</p>
            </div>
        );
    }

    const formatTime = (secs) => {
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const filteredChunks = filter
        ? chunks.filter(c => c.text?.toLowerCase().includes(filter.toLowerCase()))
        : chunks;

    return (
        <div className="vd-transcript-panel">
            <div className="vd-transcript-toolbar">
                <div className="vd-transcript-search">
                    <Icons.Search size={14} />
                    <input
                        type="text"
                        placeholder="Search transcript..."
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        className="vd-transcript-search-input"
                    />
                    {filter && (
                        <button className="vd-transcript-clear" onClick={() => setFilter('')}>
                            <Icons.Close size={12} />
                        </button>
                    )}
                </div>
                <span className="vd-chunk-count">{chunks.length} segments</span>
            </div>
            <div className="vd-transcript-list">
                {filteredChunks.map((chunk, idx) => (
                    <div key={idx} className="vd-transcript-chunk">
                        <span className="vd-transcript-time">
                            {formatTime(chunk.start_time ?? chunk.start)}
                        </span>
                        <span className={`vd-transcript-text ${language === 'hindi' ? 'hindi-text' : ''}`}>
                            {chunk.text}
                        </span>
                    </div>
                ))}
                {filteredChunks.length === 0 && (
                    <p className="vd-transcript-empty">No matching segments found</p>
                )}
            </div>
        </div>
    );
}

function VideoDetail({ videoId, onBack }) {
    const [video, setVideo] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [language, setLanguage] = useState('hindi');
    const [activeTab, setActiveTab] = useState('summary');
    const [generatingSummary, setGeneratingSummary] = useState(false);

    useEffect(() => {
        if (videoId) {
            loadVideo();
        }
    }, [videoId]);

    const loadVideo = async () => {
        setLoading(true);
        setError(null);

        try {
            const data = await getVideo(videoId, 'hi');

            setVideo({
                ...data,
                summary: {
                    hindi: data.summary_hi || data.summary || '',
                    english: data.summary_en || ''
                },
                explanation: {
                    hindi: data.explanation_hi || data.explanation || '',
                    english: data.explanation_en || ''
                }
            });
        } catch (err) {
            setError(err.message || 'Failed to load video');
        } finally {
            setLoading(false);
        }
    };

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

    const hasVideo = !!video.video_url;

    return (
        <div className="video-detail-single">
            {/* Compact Header */}
            <div className="vd-header">
                <button className="btn btn-ghost vd-back" onClick={onBack}>
                    <Icons.Back size={18} />
                    Back
                </button>

                <div className="vd-title-area">
                    <h1 className="vd-title">
                        {language === 'english' ? (video.title_en || video.title) : (video.title_hi || video.title)}
                    </h1>
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

            {/* Main Content */}
            <div className="vd-grid">
                {/* Left Column: Video + Content */}
                <div className="vd-left">
                    {/* YouTube / Video Player */}
                    {hasVideo ? (
                        <div className="vd-video-section">
                            <YouTubePlayer videoUrl={video.video_url} />
                        </div>
                    ) : (
                        <div className="vd-video-section">
                            <div className="vd-audio-banner">
                                <Icons.Music size={24} />
                                <div className="vd-audio-banner-text">
                                    <span className="vd-audio-banner-title">Audio Discourse</span>
                                    <span className="vd-audio-banner-sub">
                                        {formatDuration(video.duration)} • Read summary &amp; ask questions below
                                    </span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Description */}
                    {(video.description_hi || video.description) && (
                        <p className={`vd-description ${language === 'hindi' ? 'hindi-text' : ''}`}>
                            {language === 'english'
                                ? (video.description_en || video.description)
                                : (video.description_hi || video.description)}
                        </p>
                    )}

                    {/* Content Tabs */}
                    <div className="vd-tabs">
                        <button
                            className={`vd-tab ${activeTab === 'summary' ? 'active' : ''}`}
                            onClick={() => setActiveTab('summary')}
                        >
                            <Icons.Summary size={16} /> Summary
                        </button>
                        <button
                            className={`vd-tab ${activeTab === 'explanation' ? 'active' : ''}`}
                            onClick={() => setActiveTab('explanation')}
                        >
                            <Icons.Explanation size={16} /> Explanation
                        </button>
                        <button
                            className={`vd-tab ${activeTab === 'transcript' ? 'active' : ''}`}
                            onClick={() => setActiveTab('transcript')}
                        >
                            <Icons.Transcript size={16} /> Transcript
                        </button>
                    </div>

                    {/* Tab Content */}
                    <div className="vd-tab-content">
                        {activeTab === 'summary' && (
                            <div className={`vd-section-content ${language === 'hindi' ? 'hindi-text' : ''}`}>
                                {currentSummary ? (
                                    <div>{formatText(currentSummary)}</div>
                                ) : (
                                    <div className="vd-empty">
                                        <Icons.Summary size={32} />
                                        <p>Summary not available</p>
                                        <button
                                            className="btn btn-primary btn-sm"
                                            onClick={async () => {
                                                setGeneratingSummary(true);
                                                try {
                                                    await generateVideoSummary(videoId);
                                                    setTimeout(() => loadVideo(), 5000);
                                                    setTimeout(() => loadVideo(), 15000);
                                                } catch (e) {
                                                    console.error('Generate failed:', e);
                                                }
                                                setGeneratingSummary(false);
                                            }}
                                            disabled={generatingSummary}
                                        >
                                            {generatingSummary ? (
                                                <><Icons.Loading size={14} className="animate-spin" /> Generating...</>
                                            ) : (
                                                <><Icons.Sparkles size={14} /> Generate Summary</>
                                            )}
                                        </button>
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === 'explanation' && (
                            <div className={`vd-section-content ${language === 'hindi' ? 'hindi-text' : ''}`}>
                                {currentExplanation ? (
                                    <div>{formatText(currentExplanation)}</div>
                                ) : (
                                    <div className="vd-empty">
                                        <Icons.Explanation size={32} />
                                        <p>Explanation not available</p>
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === 'transcript' && (
                            <TranscriptViewer
                                chunks={video.transcript_chunks}
                                language={language}
                            />
                        )}
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

export { getYouTubeId };
export default VideoDetail;

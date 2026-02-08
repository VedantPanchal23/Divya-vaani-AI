import { useEffect, useRef, useState } from 'react';
import TextToSpeech from './TextToSpeech';
import { Icons } from './Icons';

function TranscriptViewer({ transcript, segments, currentTime, onSeek }) {
    const containerRef = useRef(null);
    const activeRef = useRef(null);
    const [autoScroll, setAutoScroll] = useState(true);
    const lastUserScrollRef = useRef(0);
    const scrollTimeoutRef = useRef(null);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    // Clear scroll timeout on unmount
    useEffect(() => {
        return () => {
            if (scrollTimeoutRef.current) {
                clearTimeout(scrollTimeoutRef.current);
            }
        };
    }, []);

    // Handle user manual scroll - disable auto-scroll temporarily
    const handleScroll = () => {
        lastUserScrollRef.current = Date.now();
        // Disable auto-scroll for 5 seconds after manual scroll
        setAutoScroll(false);
        if (scrollTimeoutRef.current) {
            clearTimeout(scrollTimeoutRef.current);
        }
        scrollTimeoutRef.current = setTimeout(() => {
            if (Date.now() - lastUserScrollRef.current >= 4900) {
                setAutoScroll(true);
            }
        }, 5000);
    };

    // Auto-scroll to active segment - ONLY within the transcript container
    useEffect(() => {
        if (!autoScroll) return;
        if (!activeRef.current || !containerRef.current) return;

        // Use scrollIntoView with 'nearest' to avoid page-level scrolling
        // Also ensure we're only scrolling within the container
        const container = containerRef.current;
        const activeElement = activeRef.current;

        // Calculate if active element is visible within container
        const containerRect = container.getBoundingClientRect();
        const activeRect = activeElement.getBoundingClientRect();

        const isVisible = (
            activeRect.top >= containerRect.top &&
            activeRect.bottom <= containerRect.bottom
        );

        // Only scroll if not visible
        if (!isVisible) {
            // Scroll within container only, not the whole page
            const scrollTop = activeElement.offsetTop - container.offsetTop - (containerRect.height / 3);
            container.scrollTo({
                top: Math.max(0, scrollTop),
                behavior: 'smooth'
            });
        }
    }, [currentTime, autoScroll]);

    const isSegmentActive = (segment) => {
        const start = segment.start_time ?? segment.start ?? 0;
        const end = segment.end_time ?? segment.end ?? 0;
        return currentTime >= start && currentTime < end;
    };

    // If we have segments, render with timestamps
    if (segments && segments.length > 0) {
        return (
            <div
                className="transcript-container"
                ref={containerRef}
                onScroll={handleScroll}
            >
                {!autoScroll && (
                    <button
                        className="btn btn-ghost btn-sm auto-scroll-btn"
                        onClick={() => setAutoScroll(true)}
                        style={{
                            position: 'sticky',
                            top: 0,
                            zIndex: 10,
                            width: '100%',
                            marginBottom: 'var(--spacing-sm)',
                            background: 'var(--color-bg-card)',
                            borderBottom: '1px solid var(--border-color)'
                        }}
                    >
                        <Icons.Refresh size={14} />
                        Resume auto-scroll
                    </button>
                )}
                {segments.map((segment, index) => {
                    const startTime = segment.start_time ?? segment.start ?? 0;
                    return (
                        <div
                            key={index}
                            ref={isSegmentActive(segment) ? activeRef : null}
                            className={`transcript-segment ${isSegmentActive(segment) ? 'active' : ''}`}
                            onClick={() => onSeek(startTime)}
                        >
                            <span className="transcript-timestamp">
                                <Icons.Clock size={12} style={{ marginRight: '4px', opacity: 0.7 }} />
                                {formatTime(startTime)}
                            </span>
                            <span>{segment.text}</span>
                        </div>
                    );
                })}
            </div>
        );
    }

    // Plain transcript without segments
    return (
        <div>
            <div style={{
                display: 'flex',
                justifyContent: 'flex-end',
                marginBottom: 'var(--spacing-sm)'
            }}>
                <TextToSpeech text={transcript} />
            </div>
            <div className="transcript-container" ref={containerRef}>
                <p style={{ whiteSpace: 'pre-wrap', lineHeight: 2 }}>
                    {transcript}
                </p>
            </div>
        </div>
    );
}

export default TranscriptViewer;

import { useState, useEffect, useRef } from 'react';
import { Icons } from './Icons';
import {
    addYouTubeVideo,
    getYouTubeJobStatus,
    listYouTubeJobs,
    deleteVideo,
    regenerateVideoContent,
    getVideos
} from '../api';

// ========== YouTube URL Input ==========
function YouTubeInput({ onSubmit, disabled }) {
    const [url, setUrl] = useState('');
    const [speaker, setSpeaker] = useState('Maharaj Ji');
    const [category, setCategory] = useState('pravachan');
    const [error, setError] = useState('');

    const handleSubmit = (e) => {
        e.preventDefault();
        setError('');

        if (!url.trim()) {
            setError('Please enter a YouTube URL');
            return;
        }

        // Basic URL validation
        const ytPattern = /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})/;
        if (!ytPattern.test(url.trim())) {
            setError('Invalid YouTube URL. Please paste a valid YouTube link.');
            return;
        }

        onSubmit(url.trim(), speaker.trim(), category);
        setUrl('');
    };

    return (
        <form className="admin-yt-form" onSubmit={handleSubmit}>
            <div className="admin-yt-url-row">
                <div className="admin-yt-url-input-wrap">
                    <Icons.Video size={18} />
                    <input
                        type="text"
                        value={url}
                        onChange={(e) => { setUrl(e.target.value); setError(''); }}
                        placeholder="Paste YouTube URL here..."
                        className="admin-yt-url-input"
                        disabled={disabled}
                    />
                </div>
                <button
                    type="submit"
                    className="btn btn-primary admin-yt-submit"
                    disabled={disabled || !url.trim()}
                >
                    {disabled ? (
                        <><Icons.Loading size={16} className="animate-spin" /> Processing...</>
                    ) : (
                        <><Icons.Plus size={16} /> Add Video</>
                    )}
                </button>
            </div>

            <div className="admin-yt-options">
                <div className="admin-yt-field">
                    <label>Speaker</label>
                    <input
                        type="text"
                        value={speaker}
                        onChange={(e) => setSpeaker(e.target.value)}
                        placeholder="Speaker name"
                        disabled={disabled}
                    />
                </div>
                <div className="admin-yt-field">
                    <label>Category</label>
                    <select value={category} onChange={(e) => setCategory(e.target.value)} disabled={disabled}>
                        <option value="pravachan">Pravachan</option>
                        <option value="satsang">Satsang</option>
                        <option value="kirtan">Kirtan</option>
                        <option value="lecture">Lecture</option>
                    </select>
                </div>
            </div>

            {error && <p className="admin-yt-error">{error}</p>}
        </form>
    );
}


// ========== Processing Job Card ==========
function JobCard({ job }) {
    const stepLabels = {
        queued: 'Queued',
        downloading: 'Downloading Audio',
        transcribing: 'Transcribing',
        indexing: 'Indexing for Search',
        summarizing: 'Generating Summary',
        explaining: 'Generating Explanation',
        finalizing: 'Saving Content',
        complete: 'Complete',
        error: 'Failed',
    };

    const isActive = job.status === 'processing' || job.status === 'queued';
    const isComplete = job.status === 'complete';
    const isError = job.status === 'error';

    return (
        <div className={`admin-job-card ${isComplete ? 'complete' : ''} ${isError ? 'error' : ''}`}>
            <div className="admin-job-header">
                <div className="admin-job-title">
                    {isActive && <Icons.Loading size={16} className="animate-spin" />}
                    {isComplete && <Icons.Check size={16} />}
                    {isError && <Icons.Error size={16} />}
                    <span>{job.title || 'Processing...'}</span>
                </div>
                <span className={`admin-job-badge ${job.status}`}>
                    {stepLabels[job.step] || job.step}
                </span>
            </div>

            {isActive && (
                <div className="admin-job-progress">
                    <div className="admin-job-progress-bar">
                        <div
                            className="admin-job-progress-fill"
                            style={{ width: `${job.progress}%` }}
                        />
                    </div>
                    <span className="admin-job-progress-text">{job.progress}%</span>
                </div>
            )}

            <p className="admin-job-message">{job.message}</p>

            {isComplete && job.result && (
                <div className="admin-job-result">
                    <span>✅ {job.result.chunks_count} segments transcribed</span>
                    <span>• {Math.round(job.result.duration / 60)}m duration</span>
                    {job.result.has_summary && <span>• Summary generated</span>}
                </div>
            )}
        </div>
    );
}


// ========== Video Management Table ==========
function VideoTable({ videos, onDelete, onRegenerate, deletingId, regeneratingId }) {
    const formatDuration = (secs) => {
        if (!secs) return '--:--';
        const m = Math.floor(secs / 60);
        const s = Math.floor(secs % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    if (!videos.length) {
        return (
            <div className="admin-empty">
                <Icons.Video size={48} />
                <p>No videos yet. Add one above!</p>
            </div>
        );
    }

    return (
        <div className="admin-video-table-wrap">
            <table className="admin-video-table">
                <thead>
                    <tr>
                        <th>Video</th>
                        <th>Duration</th>
                        <th>Summary</th>
                        <th>Video URL</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {videos.map(v => (
                        <tr key={v.id}>
                            <td className="admin-video-info">
                                <strong className="admin-video-name">{v.title_hi || v.title}</strong>
                                <span className="admin-video-sub">{v.speaker} • {v.category}</span>
                            </td>
                            <td>{formatDuration(v.duration)}</td>
                            <td>
                                {v.summary_hi || v.summary_en ? (
                                    <span className="admin-badge-ok">✓ Yes</span>
                                ) : (
                                    <span className="admin-badge-no">✗ No</span>
                                )}
                            </td>
                            <td>
                                {v.video_url ? (
                                    <a href={v.video_url} target="_blank" rel="noopener noreferrer" className="admin-link">
                                        YouTube ↗
                                    </a>
                                ) : (
                                    <span className="admin-badge-no">None</span>
                                )}
                            </td>
                            <td className="admin-video-actions">
                                <button
                                    className="btn btn-ghost btn-sm"
                                    title="Regenerate summary & explanation"
                                    onClick={() => onRegenerate(v.id)}
                                    disabled={regeneratingId === v.id}
                                >
                                    {regeneratingId === v.id ? (
                                        <Icons.Loading size={14} className="animate-spin" />
                                    ) : (
                                        <Icons.Sparkles size={14} />
                                    )}
                                </button>
                                <button
                                    className="btn btn-ghost btn-sm admin-delete-btn"
                                    title="Delete video"
                                    onClick={() => onDelete(v.id, v.title_hi || v.title)}
                                    disabled={deletingId === v.id}
                                >
                                    {deletingId === v.id ? (
                                        <Icons.Loading size={14} className="animate-spin" />
                                    ) : (
                                        <Icons.Close size={14} />
                                    )}
                                </button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}


// ========== Main Admin Panel ==========
function AdminPanel({ onBack }) {
    const [videos, setVideos] = useState([]);
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [deletingId, setDeletingId] = useState(null);
    const [regeneratingId, setRegeneratingId] = useState(null);
    const [confirmDelete, setConfirmDelete] = useState(null);
    const pollRef = useRef(null);

    // Load data on mount
    useEffect(() => {
        loadData();
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);

    // Poll active jobs
    useEffect(() => {
        const activeJobs = jobs.filter(j => j.status === 'processing' || j.status === 'queued');
        
        if (activeJobs.length > 0) {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = setInterval(async () => {
                try {
                    const { jobs: updated } = await listYouTubeJobs();
                    setJobs(updated);
                    
                    // If any job just completed, refresh videos list
                    const nowComplete = updated.filter(j => j.status === 'complete');
                    const wasComplete = jobs.filter(j => j.status === 'complete');
                    if (nowComplete.length > wasComplete.length) {
                        loadVideos();
                    }
                    
                    // Stop polling if no more active jobs
                    const stillActive = updated.filter(j => j.status === 'processing' || j.status === 'queued');
                    if (stillActive.length === 0 && pollRef.current) {
                        clearInterval(pollRef.current);
                        pollRef.current = null;
                    }
                } catch (e) {
                    console.error('Poll failed:', e);
                }
            }, 3000);
        }

        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
        };
    }, [jobs.length, jobs.filter(j => j.status === 'complete').length]);

    const loadData = async () => {
        setLoading(true);
        await Promise.all([loadVideos(), loadJobs()]);
        setLoading(false);
    };

    const loadVideos = async () => {
        try {
            const data = await getVideos();
            setVideos(data.videos || []);
        } catch (e) {
            console.error('Failed to load videos:', e);
        }
    };

    const loadJobs = async () => {
        try {
            const data = await listYouTubeJobs();
            setJobs(data.jobs || []);
        } catch (e) {
            console.error('Failed to load jobs:', e);
        }
    };

    const handleSubmitYouTube = async (url, speaker, category) => {
        setSubmitting(true);
        try {
            const result = await addYouTubeVideo(url, speaker, category);
            // Add the new job to our list
            setJobs(prev => [{
                job_id: result.job_id,
                status: 'queued',
                step: 'queued',
                progress: 0,
                message: 'Queued for processing...',
                title: result.title,
                youtube_id: result.youtube_id,
                created_at: new Date().toISOString(),
            }, ...prev]);
        } catch (e) {
            alert(`Error: ${e.message}`);
        } finally {
            setSubmitting(false);
        }
    };

    const handleDelete = async (videoId) => {
        setConfirmDelete(null);
        setDeletingId(videoId);
        try {
            await deleteVideo(videoId);
            setVideos(prev => prev.filter(v => v.id !== videoId));
        } catch (e) {
            alert(`Delete failed: ${e.message}`);
        } finally {
            setDeletingId(null);
        }
    };

    const handleRegenerate = async (videoId) => {
        setRegeneratingId(videoId);
        try {
            await regenerateVideoContent(videoId);
            // Reload after a delay for content to generate
            setTimeout(loadVideos, 10000);
        } catch (e) {
            alert(`Regenerate failed: ${e.message}`);
        } finally {
            setRegeneratingId(null);
        }
    };

    const activeJobs = jobs.filter(j => j.status === 'processing' || j.status === 'queued');
    const recentJobs = jobs.slice(0, 10);

    return (
        <div className="admin-panel">
            {/* Header */}
            <div className="admin-header">
                <button className="btn btn-ghost admin-back" onClick={onBack}>
                    <Icons.Back size={18} /> Back
                </button>
                <div className="admin-header-title">
                    <h1>🔧 Admin Panel</h1>
                    <p>Manage discourses — add YouTube videos, view processing status</p>
                </div>
                <div className="admin-stats">
                    <span className="admin-stat">{videos.length} Videos</span>
                    {activeJobs.length > 0 && (
                        <span className="admin-stat active">
                            <Icons.Loading size={12} className="animate-spin" />
                            {activeJobs.length} Processing
                        </span>
                    )}
                </div>
            </div>

            {/* Add YouTube Video */}
            <section className="admin-section">
                <h2 className="admin-section-title">
                    <Icons.Plus size={20} /> Add YouTube Video
                </h2>
                <p className="admin-section-desc">
                    Paste a YouTube URL. The system will automatically download audio, transcribe it, 
                    generate summary & explanation, and make it available for Q&A.
                </p>
                <YouTubeInput onSubmit={handleSubmitYouTube} disabled={submitting} />
            </section>

            {/* Active Processing Jobs */}
            {recentJobs.length > 0 && (
                <section className="admin-section">
                    <h2 className="admin-section-title">
                        <Icons.Clock size={20} /> Processing Queue
                    </h2>
                    <div className="admin-jobs-list">
                        {recentJobs.map(job => (
                            <JobCard key={job.job_id} job={job} />
                        ))}
                    </div>
                </section>
            )}

            {/* Video Management */}
            <section className="admin-section">
                <h2 className="admin-section-title">
                    <Icons.Video size={20} /> All Videos ({videos.length})
                </h2>
                {loading ? (
                    <div className="admin-loading">
                        <Icons.Loading size={32} className="animate-spin" />
                        <p>Loading videos...</p>
                    </div>
                ) : (
                    <VideoTable
                        videos={videos}
                        onDelete={(id, title) => setConfirmDelete({ id, title })}
                        onRegenerate={handleRegenerate}
                        deletingId={deletingId}
                        regeneratingId={regeneratingId}
                    />
                )}
            </section>

            {/* Delete Confirmation Dialog */}
            {confirmDelete && (
                <div className="confirm-overlay" onClick={() => setConfirmDelete(null)}>
                    <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
                        <p>Delete "<strong>{confirmDelete.title}</strong>"?</p>
                        <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                            This will permanently remove the video, transcript, and all generated content.
                        </p>
                        <div className="confirm-actions">
                            <button className="btn btn-ghost" onClick={() => setConfirmDelete(null)}>
                                Cancel
                            </button>
                            <button
                                className="btn btn-primary"
                                style={{ background: 'var(--color-error)' }}
                                onClick={() => handleDelete(confirmDelete.id)}
                            >
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default AdminPanel;

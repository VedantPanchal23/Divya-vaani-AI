import { useState, useRef, useEffect } from 'react';
import { uploadYouTubeVideo, uploadFile, getUploadStatus } from '../api';
import { Icons } from './Icons';

const STEPS = {
    downloading: { label: 'Downloading', pct: 5 },
    transcribing: { label: 'Transcribing', pct: 30 },
    summarizing: { label: 'Summarizing', pct: 60 },
    explaining: { label: 'Explaining', pct: 75 },
    generating_themes: { label: 'Extracting themes', pct: 90 },
    done: { label: 'Complete', pct: 100 },
};

function AdminUpload({ onClose, onUploadComplete }) {
    const [tab, setTab] = useState('youtube'); // 'youtube' | 'file'
    const [adminKey, setAdminKey] = useState(() => localStorage.getItem('dv_admin_key') || '');
    const [youtubeUrl, setYoutubeUrl] = useState('');
    const [customTitle, setCustomTitle] = useState('');
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState(null);
    const [job, setJob] = useState(null); // { file_id, status, step, progress, message }
    const [success, setSuccess] = useState(false);
    const fileInputRef = useRef(null);
    const pollRef = useRef(null);

    // Persist admin key
    useEffect(() => {
        if (adminKey) localStorage.setItem('dv_admin_key', adminKey);
    }, [adminKey]);

    // Cleanup polling on unmount
    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);

    const startPolling = (fileId) => {
        if (pollRef.current) clearInterval(pollRef.current);

        pollRef.current = setInterval(async () => {
            try {
                const data = await getUploadStatus(fileId);
                pollRef._failCount = 0; // Reset on success
                if (data.status === 'complete') {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                    setJob({ file_id: fileId, status: 'complete', step: 'done', progress: 100, message: 'Processing complete!' });
                    setSuccess(true);
                    setUploading(false);
                    onUploadComplete?.();
                } else if (data.status === 'error') {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                    setError(data.message || 'Processing failed');
                    setUploading(false);
                } else {
                    setJob({
                        file_id: fileId,
                        status: data.status,
                        step: data.step || 'processing',
                        progress: data.progress || 0,
                        message: data.message || 'Processing...',
                    });
                }
            } catch (err) {
                // Stop polling after repeated failures
                if (!pollRef._failCount) pollRef._failCount = 0;
                pollRef._failCount++;
                console.warn(`Status poll failed (${pollRef._failCount}):`, err.message);
                if (pollRef._failCount >= 5) {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                    setError(`Lost connection to server: ${err.message}`);
                    setUploading(false);
                }
            }
        }, 3000);
    };

    const handleYouTubeSubmit = async () => {
        if (!youtubeUrl.trim()) {
            setError('Please enter a YouTube URL');
            return;
        }
        if (!adminKey.trim()) {
            setError('Admin API key is required');
            return;
        }
        setError(null);
        setSuccess(false);
        setUploading(true);

        try {
            const result = await uploadYouTubeVideo(youtubeUrl.trim(), customTitle.trim(), adminKey.trim());
            setJob({
                file_id: result.file_id,
                status: 'processing',
                step: 'downloading',
                progress: 0,
                message: result.message || 'Download started...',
            });
            startPolling(result.file_id);
        } catch (err) {
            setError(err.message || 'Failed to start YouTube upload');
            setUploading(false);
        }
    };

    const handleFileSubmit = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (!adminKey.trim()) {
            setError('Admin API key is required');
            return;
        }
        setError(null);
        setSuccess(false);
        setUploading(true);

        try {
            const result = await uploadFile(file, adminKey.trim());
            setJob({
                file_id: result.file_id,
                status: 'processing',
                step: 'transcribing',
                progress: 0,
                message: result.message || 'Processing started...',
            });
            startPolling(result.file_id);
        } catch (err) {
            setError(err.message || 'Upload failed');
            setUploading(false);
        }
    };

    const stepInfo = STEPS[job?.step] || { label: job?.step || 'Processing', pct: job?.progress || 0 };
    const progressPct = job?.progress || stepInfo.pct;

    const handleReset = () => {
        setJob(null);
        setSuccess(false);
        setError(null);
        setUploading(false);
        setYoutubeUrl('');
        setCustomTitle('');
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    return (
        <div className="admin-upload-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="admin-upload-modal">
                <div className="admin-upload-header">
                    <h2>Upload Content</h2>
                    <button className="btn btn-ghost btn-sm" onClick={onClose} title="Close">
                        <Icons.Close size={18} />
                    </button>
                </div>

                {/* Admin Key */}
                <div className="admin-upload-field">
                    <label>Admin API Key</label>
                    <input
                        type="password"
                        value={adminKey}
                        onChange={(e) => setAdminKey(e.target.value)}
                        placeholder="Enter admin API key..."
                        className="admin-upload-input"
                    />
                </div>

                {/* Tab Switcher */}
                <div className="admin-upload-tabs">
                    <button
                        className={`admin-upload-tab ${tab === 'youtube' ? 'active' : ''}`}
                        onClick={() => { setTab('youtube'); setError(null); }}
                        disabled={uploading}
                    >
                        <Icons.Play size={14} />
                        YouTube Link
                    </button>
                    <button
                        className={`admin-upload-tab ${tab === 'file' ? 'active' : ''}`}
                        onClick={() => { setTab('file'); setError(null); }}
                        disabled={uploading}
                    >
                        <Icons.Upload size={14} />
                        File Upload
                    </button>
                </div>

                {/* YouTube Tab */}
                {tab === 'youtube' && !job && (
                    <div className="admin-upload-form">
                        <div className="admin-upload-field">
                            <label>YouTube URL</label>
                            <input
                                type="url"
                                value={youtubeUrl}
                                onChange={(e) => setYoutubeUrl(e.target.value)}
                                placeholder="https://youtube.com/watch?v=... or https://youtu.be/..."
                                className="admin-upload-input"
                                disabled={uploading}
                            />
                        </div>
                        <div className="admin-upload-field">
                            <label>Custom Title (optional)</label>
                            <input
                                type="text"
                                value={customTitle}
                                onChange={(e) => setCustomTitle(e.target.value)}
                                placeholder="Leave empty to use YouTube title"
                                className="admin-upload-input"
                                disabled={uploading}
                            />
                        </div>
                        <button
                            className="btn btn-primary admin-upload-submit"
                            onClick={handleYouTubeSubmit}
                            disabled={uploading || !youtubeUrl.trim()}
                        >
                            {uploading ? (
                                <><Icons.Loading size={14} className="animate-spin" /> Processing...</>
                            ) : (
                                <><Icons.Play size={14} /> Download & Process</>
                            )}
                        </button>
                    </div>
                )}

                {/* File Tab */}
                {tab === 'file' && !job && (
                    <div className="admin-upload-form">
                        <div className="admin-upload-dropzone" onClick={() => fileInputRef.current?.click()}>
                            <Icons.Upload size={32} />
                            <p>Click to select audio/video file</p>
                            <span>MP3, MP4, WAV, M4A, WebM, OGG, FLAC (max {500}MB)</span>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept=".mp3,.mp4,.wav,.m4a,.webm,.ogg,.flac"
                                onChange={handleFileSubmit}
                                style={{ display: 'none' }}
                                disabled={uploading}
                            />
                        </div>
                    </div>
                )}

                {/* Processing Status */}
                {job && !success && (
                    <div className="admin-upload-status">
                        <div className="admin-upload-status-header">
                            <Icons.Loading size={18} className="animate-spin" />
                            <span>{job.message}</span>
                        </div>
                        <div className="admin-upload-progress">
                            <div className="admin-upload-progress-bar" style={{ width: `${progressPct}%` }} />
                        </div>
                        <div className="admin-upload-progress-label">
                            {stepInfo.label} — {progressPct}%
                        </div>
                    </div>
                )}

                {/* Success */}
                {success && (
                    <div className="admin-upload-success">
                        <Icons.Check size={32} />
                        <h3>Upload Complete!</h3>
                        <p>The discourse has been processed and is now available.</p>
                        <button className="btn btn-primary" onClick={handleReset}>
                            Upload Another
                        </button>
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div className="admin-upload-error">
                        <Icons.Error size={16} />
                        <span>{error}</span>
                    </div>
                )}
            </div>
        </div>
    );
}

export default AdminUpload;

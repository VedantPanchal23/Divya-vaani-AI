import { useState, useRef, useEffect } from 'react';
import { uploadFile } from '../api';
import { Icons } from './Icons';

function Upload({ onSuccess }) {
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const fileInputRef = useRef(null);
    const progressIntervalRef = useRef(null);

    // Clear interval on unmount
    useEffect(() => {
        return () => {
            if (progressIntervalRef.current) {
                clearInterval(progressIntervalRef.current);
            }
        };
    }, []);

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = () => {
        setIsDragging(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragging(false);
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    };

    const handleFileSelect = (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    };

    const handleFile = async (file) => {
        // Validate file type
        const validTypes = ['audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/m4a', 'video/mp4', 'video/webm', 'audio/ogg'];
        const ext = file.name.split('.').pop().toLowerCase();
        const validExts = ['mp3', 'mp4', 'm4a', 'wav', 'webm', 'ogg'];

        if (!validExts.includes(ext)) {
            alert('Please upload an audio or video file (MP3, MP4, WAV, M4A, WebM, or OGG)');
            return;
        }

        setIsUploading(true);
        setProgress(0);

        try {
            // Simulate progress (actual progress would come from XMLHttpRequest)
            progressIntervalRef.current = setInterval(() => {
                setProgress(prev => {
                    if (prev >= 90) {
                        clearInterval(progressIntervalRef.current);
                        return 90;
                    }
                    return prev + 10;
                });
            }, 200);

            const result = await uploadFile(file);

            clearInterval(progressIntervalRef.current);
            setProgress(100);

            setTimeout(() => {
                setIsUploading(false);
                setProgress(0);
                onSuccess?.(result);
            }, 500);
        } catch (error) {
            console.error('Upload failed:', error);
            alert(`Upload failed: ${error.message}`);
            setIsUploading(false);
            setProgress(0);
        }
    };

    return (
        <div>
            <div className="card-header">
                <h3 className="card-title">
                    <Icons.Upload size={18} className="card-title-icon" />
                    Upload Audio/Video
                </h3>
            </div>

            <div
                className={`upload-zone ${isDragging ? 'drag-over' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    accept=".mp3,.mp4,.m4a,.wav,.webm,.ogg"
                    onChange={handleFileSelect}
                    style={{ display: 'none' }}
                />

                {isUploading ? (
                    <div className="upload-progress">
                        <Icons.Loading size={40} className="animate-spin" style={{ color: 'var(--color-accent-primary)', marginBottom: '1rem' }} />
                        <p className="upload-text">Uploading... {progress}%</p>
                        <div className="progress-bar">
                            <div
                                className="progress-fill"
                                style={{ width: `${progress}%` }}
                            />
                        </div>
                    </div>
                ) : (
                    <>
                        <div className="upload-icon">
                            <Icons.Upload size={48} style={{ color: 'var(--color-accent-primary)' }} />
                        </div>
                        <p className="upload-text">
                            Drag & drop or click to upload
                        </p>
                        <p className="upload-hint">
                            MP3, MP4, WAV, M4A, WebM, OGG
                        </p>
                    </>
                )}
            </div>
        </div>
    );
}

export default Upload;

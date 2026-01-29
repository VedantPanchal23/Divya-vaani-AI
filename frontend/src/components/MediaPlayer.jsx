import { forwardRef, useState, useEffect } from 'react';
import { Icons } from './Icons';
import { FiRewind, FiFastForward } from 'react-icons/fi';

const MediaPlayer = forwardRef(({ url, type, onTimeUpdate }, ref) => {
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);

    const formatTime = (seconds) => {
        if (!seconds || isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const handleTimeUpdate = () => {
        if (ref?.current) {
            const time = ref.current.currentTime;
            setCurrentTime(time);
            onTimeUpdate?.(time);
        }
    };

    const handleLoadedMetadata = () => {
        if (ref?.current) {
            setDuration(ref.current.duration);
        }
    };

    const handlePlayPause = () => {
        if (ref?.current) {
            if (isPlaying) {
                ref.current.pause();
            } else {
                ref.current.play();
            }
            setIsPlaying(!isPlaying);
        }
    };

    const handleProgressClick = (e) => {
        if (ref?.current && duration) {
            const rect = e.currentTarget.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const percentage = x / rect.width;
            ref.current.currentTime = percentage * duration;
        }
    };

    const handleSkip = (seconds) => {
        if (ref?.current) {
            ref.current.currentTime = Math.max(0, Math.min(duration, ref.current.currentTime + seconds));
        }
    };

    const isVideo = type === 'mp4' || type === 'webm';

    return (
        <div className="media-player">
            {isVideo ? (
                <video
                    ref={ref}
                    src={url}
                    onTimeUpdate={handleTimeUpdate}
                    onLoadedMetadata={handleLoadedMetadata}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    style={{ width: '100%', maxHeight: '300px', borderRadius: 'var(--radius-md)' }}
                />
            ) : (
                <audio
                    ref={ref}
                    src={url}
                    onTimeUpdate={handleTimeUpdate}
                    onLoadedMetadata={handleLoadedMetadata}
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    style={{ display: 'none' }}
                />
            )}

            <div className="player-controls">
                <button
                    className="btn btn-ghost btn-icon"
                    onClick={() => handleSkip(-10)}
                    title="Rewind 10s"
                >
                    <FiRewind size={18} />
                </button>

                <button
                    className="btn btn-primary btn-icon"
                    onClick={handlePlayPause}
                >
                    {isPlaying ? <Icons.Pause size={20} /> : <Icons.Play size={20} />}
                </button>

                <button
                    className="btn btn-ghost btn-icon"
                    onClick={() => handleSkip(10)}
                    title="Forward 10s"
                >
                    <FiFastForward size={18} />
                </button>

                <span className="player-time">{formatTime(currentTime)}</span>

                <div
                    className="player-progress"
                    onClick={handleProgressClick}
                >
                    <div
                        className="player-progress-fill"
                        style={{ width: `${duration ? (currentTime / duration) * 100 : 0}%` }}
                    />
                </div>

                <span className="player-time">{formatTime(duration)}</span>
            </div>
        </div>
    );
});

MediaPlayer.displayName = 'MediaPlayer';

export default MediaPlayer;

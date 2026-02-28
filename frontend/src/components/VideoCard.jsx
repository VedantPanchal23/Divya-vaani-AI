import { Icons } from './Icons';
import { getYouTubeId } from './VideoDetail';

function VideoCard({ video, onClick }) {
    const formatDuration = (seconds) => {
        if (!seconds) return '--:--';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (mins >= 60) {
            const hrs = Math.floor(mins / 60);
            const remainMins = mins % 60;
            return `${hrs}:${remainMins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const truncateText = (text, maxLength = 80) => {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength).trim() + '...';
    };

    // Auto-detect YouTube thumbnail
    const ytId = getYouTubeId(video.video_url);
    const thumbnailSrc = ytId
        ? `https://img.youtube.com/vi/${ytId}/hqdefault.jpg`
        : (video.thumbnail || '/api/thumbnail/default');
    const hasVideo = !!video.video_url;

    return (
        <div className="video-card" onClick={() => onClick?.(video)}>
            <div className="video-card-thumbnail">
                <img 
                    src={thumbnailSrc} 
                    alt={video.title}
                    onError={(e) => {
                        e.target.src = 'data:image/svg+xml,' + encodeURIComponent(`
                            <svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
                                <defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" style="stop-color:#e67e22"/><stop offset="100%" style="stop-color:#f39c12"/></linearGradient></defs>
                                <rect fill="url(#g)" width="320" height="180" rx="8"/>
                                <text x="50%" y="44%" dominant-baseline="middle" text-anchor="middle" fill="white" font-size="32">🙏</text>
                                <text x="50%" y="62%" dominant-baseline="middle" text-anchor="middle" fill="rgba(255,255,255,0.9)" font-family="sans-serif" font-size="12">Spiritual Discourse</text>
                            </svg>
                        `);
                    }}
                />
                <div className="video-card-duration">
                    {hasVideo && <Icons.Video size={12} />}
                    {!hasVideo && <Icons.Music size={12} />}
                    {formatDuration(video.duration)}
                </div>
                <div className="video-card-play-overlay">
                    <Icons.Play size={40} />
                </div>
            </div>
            
            <div className="video-card-content">
                <h3 className="video-card-title" title={video.title_hi || video.title}>
                    {truncateText(video.title_hi || video.title, 60)}
                </h3>
                
                <p className="video-card-description">
                    {truncateText(video.description_hi || video.description, 100)}
                </p>
                
                <div className="video-card-meta">
                    <span className="video-card-speaker">
                        <Icons.Spiritual size={14} />
                        {video.speaker || 'Maharaj Ji'}
                    </span>
                    <span className="video-card-category">
                        {video.category || 'pravachan'}
                    </span>
                </div>

                {video.tags && video.tags.length > 0 && (
                    <div className="video-card-tags">
                        {(Array.isArray(video.tags) ? video.tags : video.tags.split(/\s+/)).slice(0, 3).map((tag, i) => (
                            <span key={i} className="video-card-tag">{tag}</span>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

export default VideoCard;

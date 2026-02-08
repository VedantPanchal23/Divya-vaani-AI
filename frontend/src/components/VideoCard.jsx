import { Icons } from './Icons';

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

    return (
        <div
            className="video-card"
            onClick={() => onClick?.(video)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onClick(video);
                }
            }}
        >
            <div className="video-card-thumbnail">
                <img 
                    src={video.thumbnail || '/api/thumbnail/default'} 
                    alt={video.title}
                    onError={(e) => {
                        e.target.src = 'data:image/svg+xml,' + encodeURIComponent(`
                            <svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
                                <rect fill="#f0f2f5" width="320" height="180"/>
                                <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#718096" font-family="sans-serif" font-size="14">&#9834; Divya Vaani</text>
                            </svg>
                        `);
                    }}
                />
                <div className="video-card-duration">
                    <Icons.Clock size={12} />
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
                        {video.tags.slice(0, 3).map((tag, i) => (
                            <span key={i} className="video-card-tag">{tag}</span>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

export default VideoCard;

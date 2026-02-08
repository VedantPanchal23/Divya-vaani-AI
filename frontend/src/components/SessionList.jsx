import { Icons } from './Icons';

function SessionList({ sessions, activeSession, onSelect, onRefresh }) {
    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'ready':
                return <Icons.Success size={16} className="status-icon success" />;
            case 'error':
                return <Icons.Error size={16} className="status-icon error" />;
            case 'transcribing':
            case 'summarizing':
            case 'explaining':
            case 'embedding':
                return <Icons.Loading size={16} className="status-icon processing animate-spin" />;
            default:
                return <Icons.Clock size={16} className="status-icon pending" />;
        }
    };

    const getFileIcon = (fileType) => {
        if (fileType === 'mp4' || fileType === 'webm') {
            return <Icons.Video size={24} />;
        }
        return <Icons.Music size={24} />;
    };

    if (!sessions || sessions.length === 0) {
        return (
            <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                <Icons.Sessions size={32} style={{ opacity: 0.4, marginBottom: '0.5rem' }} />
                <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
                    No sessions yet
                </p>
            </div>
        );
    }

    return (
        <div className="session-list">
            {sessions.map((session) => (
                <div
                    key={session.id}
                    className={`session-item ${activeSession === session.id ? 'active' : ''}`}
                    onClick={() => onSelect(session.id)}
                >
                    <span className="session-icon">
                        {getFileIcon(session.file_type)}
                    </span>
                    <div className="session-info">
                        <div className="session-name">
                            {session.filename}
                        </div>
                        <div className="session-meta">
                            {formatDate(session.created_at)}
                        </div>
                    </div>
                    <div className="session-status">
                        {getStatusIcon(session.status)}
                    </div>
                </div>
            ))}
        </div>
    );
}

export default SessionList;

import { useState, useEffect } from 'react';
import VideoCard from './components/VideoCard';
import VideoDetail from './components/VideoDetail';
import { Icons } from './components/Icons';
import { getVideos } from './api';

/* Shared header */
function AppHeader({ theme, isThemeTransitioning, toggleTheme }) {
    return (
        <header className="header">
            <div className="header-logo">
                <span className="header-logo-icon">
                    <Icons.Spiritual size={20} />
                </span>
                <span className="header-logo-text">Divya Vaani AI</span>
            </div>
            <nav className="header-nav">
                <span className="header-badge">
                    <Icons.Globe size={11} />
                    Hindi · English
                </span>
                <span className="header-badge">
                    <Icons.AI size={11} />
                    AI Powered
                </span>
                <button
                    className={`theme-toggle ${isThemeTransitioning ? 'transitioning' : ''}`}
                    onClick={toggleTheme}
                    aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
                    title={theme === 'light' ? 'Dark Mode' : 'Light Mode'}
                >
                    <span className="theme-toggle-icon">
                        {theme === 'light' ? <Icons.Moon size={16} /> : <Icons.Sun size={16} />}
                    </span>
                </button>
            </nav>
        </header>
    );
}

function App() {
    const [videos, setVideos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedVideo, setSelectedVideo] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('all');
    const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
    const [isThemeTransitioning, setIsThemeTransitioning] = useState(false);

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const toggleTheme = () => {
        setIsThemeTransitioning(true);
        setTimeout(() => setTheme(prev => prev === 'light' ? 'dark' : 'light'), 150);
        setTimeout(() => setIsThemeTransitioning(false), 500);
    };

    useEffect(() => { fetchVideos(); }, []);

    const fetchVideos = async () => {
        setLoading(true);
        try {
            const data = await getVideos();
            setVideos(data.videos || []);
        } catch (error) {
            console.error('Failed to fetch videos:', error);
        } finally {
            setLoading(false);
        }
    };

    const categories = ['all', ...new Set(videos.map(v => v.category || 'pravachan'))];

    const filteredVideos = videos.filter(video => {
        const q = searchQuery.toLowerCase();
        const matchesSearch = !searchQuery ||
            video.title?.toLowerCase().includes(q) ||
            video.title_hi?.includes(searchQuery) ||
            video.description?.toLowerCase().includes(q) ||
            video.description_hi?.includes(searchQuery) ||
            video.tags?.some(tag => tag.toLowerCase().includes(q));
        const matchesCategory = selectedCategory === 'all' || video.category === selectedCategory;
        return matchesSearch && matchesCategory;
    });

    const handleVideoClick = (video) => setSelectedVideo(video.id);
    const handleBack = () => setSelectedVideo(null);

    const headerProps = { theme, isThemeTransitioning, toggleTheme };

    if (selectedVideo) {
        return (
            <div className={`app ${isThemeTransitioning ? 'theme-transitioning' : ''}`}>
                <AppHeader {...headerProps} />
                <main className="main-detail">
                    <VideoDetail videoId={selectedVideo} onBack={handleBack} />
                </main>
            </div>
        );
    }

    return (
        <div className={`app ${isThemeTransitioning ? 'theme-transitioning' : ''}`}>
            <AppHeader {...headerProps} />

            {/* Hero */}
            <section className="hero-section">
                <div className="hero-content">
                    <h1 className="hero-title">
                        <span className="hero-title-icon"><Icons.Spiritual size={26} /></span>
                        Divya Vaani AI
                    </h1>
                    <p className="hero-subtitle">
                        Discover wisdom from Maharaj Ji's discourses — AI-powered summaries,
                        explanations, and conversations, in Hindi &amp; English.
                    </p>
                    <p className="hero-subtitle-hi">
                        दिव्य वाणी — महाराज जी के प्रवचनों का AI-संचालित ज्ञान मंच
                    </p>
                </div>
            </section>

            {/* Filters */}
            <section className="filter-section">
                <div className="filter-container">
                    <div className="search-box">
                        <Icons.Search size={16} />
                        <input
                            type="text"
                            placeholder="Search discourses... (खोजें)"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="search-input"
                        />
                        {searchQuery && (
                            <button className="search-clear" onClick={() => setSearchQuery('')}>
                                <Icons.Close size={14} />
                            </button>
                        )}
                    </div>
                    <div className="category-filters">
                        {categories.map(cat => (
                            <button
                                key={cat}
                                className={`category-btn ${selectedCategory === cat ? 'active' : ''}`}
                                onClick={() => setSelectedCategory(cat)}
                            >
                                {cat === 'all' ? 'All' : cat.charAt(0).toUpperCase() + cat.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>
            </section>

            {/* Grid */}
            <main className="main-home">
                {loading ? (
                    <div className="loading-container">
                        <Icons.Loading size={36} className="animate-spin" />
                        <p>Loading discourses...</p>
                    </div>
                ) : filteredVideos.length === 0 ? (
                    <div className="empty-container">
                        <Icons.Search size={48} />
                        <h2>No discourses found</h2>
                        <p>
                            {searchQuery
                                ? `No results for "${searchQuery}". Try a different term.`
                                : 'No discourses available yet.'}
                        </p>
                        {searchQuery && (
                            <button className="btn btn-primary" onClick={() => setSearchQuery('')}>
                                Clear Search
                            </button>
                        )}
                    </div>
                ) : (
                    <>
                        <div className="videos-header">
                            <h2 className="videos-count">
                                {filteredVideos.length} {filteredVideos.length === 1 ? 'Discourse' : 'Discourses'}
                                {selectedCategory !== 'all' && ` in ${selectedCategory}`}
                            </h2>
                        </div>
                        <div className="videos-grid">
                            {filteredVideos.map(video => (
                                <VideoCard key={video.id} video={video} onClick={handleVideoClick} />
                            ))}
                        </div>
                    </>
                )}
            </main>

            <footer className="footer">
                <p><span className="footer-brand">Divya Vaani AI</span> — Spiritual wisdom, powered by artificial intelligence</p>
            </footer>
        </div>
    );
}

export default App;

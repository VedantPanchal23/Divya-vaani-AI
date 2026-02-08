import { useState, useEffect } from 'react';
import VideoCard from './components/VideoCard';
import VideoDetail from './components/VideoDetail';
import { Icons } from './components/Icons';
import { getVideos } from './api';

function App() {
    const [videos, setVideos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedVideo, setSelectedVideo] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('all');
    const [theme, setTheme] = useState(() => {
        return localStorage.getItem('theme') || 'light';
    });
    const [isThemeTransitioning, setIsThemeTransitioning] = useState(false);

    // Apply theme on mount and change
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    const toggleTheme = () => {
        setIsThemeTransitioning(true);
        setTimeout(() => {
            setTheme(prev => prev === 'light' ? 'dark' : 'light');
        }, 150);
        setTimeout(() => {
            setIsThemeTransitioning(false);
        }, 500);
    };

    // Fetch videos on mount
    useEffect(() => {
        fetchVideos();
    }, []);

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

    // Get unique categories from videos
    const categories = ['all', ...new Set(videos.map(v => v.category || 'pravachan'))];

    // Filter videos by search and category
    const filteredVideos = videos.filter(video => {
        const matchesSearch = searchQuery === '' || 
            (video.title && video.title.toLowerCase().includes(searchQuery.toLowerCase())) ||
            (video.title_hi && video.title_hi.includes(searchQuery)) ||
            (video.description && video.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
            (video.description_hi && video.description_hi.includes(searchQuery)) ||
            (video.tags && video.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase())));
        
        const matchesCategory = selectedCategory === 'all' || video.category === selectedCategory;
        
        return matchesSearch && matchesCategory;
    });

    const handleVideoClick = (video) => {
        setSelectedVideo(video.id);
    };

    const handleBack = () => {
        setSelectedVideo(null);
    };

    // If a video is selected, show the detail view
    if (selectedVideo) {
        return (
            <div className={`app ${isThemeTransitioning ? 'theme-transitioning' : ''}`}>
                {/* Header */}
                <header className="header">
                    <div className="header-logo">
                        <span className="header-logo-icon">
                            <Icons.Spiritual size={28} />
                        </span>
                        <span className="header-logo-text">Spiritual Teachings AI</span>
                    </div>
                    <nav className="header-nav">
                        <span className="header-badge">
                            <Icons.Globe size={14} />
                            Hindi + English
                        </span>
                        <span className="header-badge">
                            <Icons.AI size={14} />
                            AI-Powered
                        </span>
                        <button
                            className={`theme-toggle ${isThemeTransitioning ? 'transitioning' : ''}`}
                            onClick={toggleTheme}
                            title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
                        >
                            <span className="theme-toggle-icon">
                                {theme === 'light' ? <Icons.Moon size={20} /> : <Icons.Sun size={20} />}
                            </span>
                        </button>
                    </nav>
                </header>

                <main className="main-detail">
                    <VideoDetail videoId={selectedVideo} onBack={handleBack} />
                </main>
            </div>
        );
    }
    // Home page with video cards
    return (
        <div className={`app ${isThemeTransitioning ? 'theme-transitioning' : ''}`}>
            {/* Header */}
            <header className="header">
                <div className="header-logo">
                    <span className="header-logo-icon">
                        <Icons.Spiritual size={28} />
                    </span>
                    <span className="header-logo-text">Spiritual Teachings AI</span>
                </div>
                <nav className="header-nav">
                    <span className="header-badge">
                        <Icons.Globe size={14} />
                        Hindi + English
                    </span>
                    <span className="header-badge">
                        <Icons.AI size={14} />
                        AI-Powered
                    </span>
                    <button
                        className={`theme-toggle ${isThemeTransitioning ? 'transitioning' : ''}`}
                        onClick={toggleTheme}
                        title={theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
                    >
                        <span className="theme-toggle-icon">
                            {theme === 'light' ? <Icons.Moon size={20} /> : <Icons.Sun size={20} />}
                        </span>
                    </button>
                </nav>
            </header>

            {/* Hero Section */}
            <section className="hero-section">
                <div className="hero-content">
                    <h1 className="hero-title">
                        <span className="hero-title-icon">🙏</span>
                        Spiritual Discourses Collection
                    </h1>
                    <p className="hero-subtitle">
                        Explore divine wisdom from Maharaj Ji's teachings. 
                        Read summaries, explanations, and ask questions powered by AI.
                    </p>
                    <p className="hero-subtitle-hi">
                        महाराज जी के प्रवचनों से दिव्य ज्ञान का अनुभव करें।
                    </p>
                </div>
            </section>

            {/* Search & Filter Section */}
            <section className="filter-section">
                <div className="filter-container">
                    <div className="search-box">
                        <Icons.Search size={20} />
                        <input
                            type="text"
                            placeholder="Search discourses... (खोजें...)"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="search-input"
                        />
                        {searchQuery && (
                            <button 
                                className="search-clear"
                                onClick={() => setSearchQuery('')}
                            >
                                <Icons.Close size={16} />
                            </button>
                        )}
                    </div>

                    <div className="category-filters">
                        {categories.map(category => (
                            <button
                                key={category}
                                className={`category-btn ${selectedCategory === category ? 'active' : ''}`}
                                onClick={() => setSelectedCategory(category)}
                            >
                                {category === 'all' ? 'All' : category.charAt(0).toUpperCase() + category.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>
            </section>

            {/* Videos Grid */}
            <main className="main-home">
                {loading ? (
                    <div className="loading-container">
                        <Icons.Loading size={48} className="animate-spin" />
                        <p>Loading spiritual discourses...</p>
                    </div>
                ) : filteredVideos.length === 0 ? (
                    <div className="empty-container">
                        <Icons.Search size={64} />
                        <h2>No Discourses Found</h2>
                        <p>
                            {searchQuery 
                                ? `No results for "${searchQuery}". Try a different search term.`
                                : 'No discourses available yet. Please check back later.'
                            }
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
                                <VideoCard
                                    key={video.id}
                                    video={video}
                                    onClick={handleVideoClick}
                                />
                            ))}
                        </div>
                    </>
                )}
            </main>

            {/* Footer */}
            <footer className="footer">
                <p>🙏 Powered by AI for spiritual learning</p>
            </footer>
        </div>
    );
}

export default App;

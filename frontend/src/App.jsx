import { useState, useEffect } from 'react';
import { Routes, Route, useNavigate, useParams } from 'react-router-dom';
import VideoCard from './components/VideoCard';
import VideoDetail from './components/VideoDetail';
import { Icons } from './components/Icons';
import { getVideos, getFavorites } from './api';
import { useAuth } from './components/AuthContext';
import AuthPage from './components/AuthPage';
import Profile from './components/Profile';

/* Shared header */
function AppHeader({ theme, isThemeTransitioning, toggleTheme, onAuthClick, onFavoritesClick, showFavorites, onProfileClick }) {
    const { user, isAuthenticated, logout } = useAuth();
    const [showUserMenu, setShowUserMenu] = useState(false);
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

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

                {isAuthenticated && (
                    <button
                        className={`header-badge header-badge-btn ${showFavorites ? 'active' : ''}`}
                        onClick={onFavoritesClick}
                        title="My Favorites"
                    >
                        <Icons.Heart size={11} />
                        Favorites
                    </button>
                )}

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

                {isAuthenticated ? (
                    <div className="user-menu-container">
                        <button
                            className="user-menu-btn"
                            onClick={() => setShowUserMenu(!showUserMenu)}
                            title={user?.display_name || user?.email}
                        >
                            <Icons.User size={16} />
                            <span className="user-menu-name">
                                {user?.display_name || user?.email?.split('@')[0]}
                            </span>
                        </button>
                        {showUserMenu && (
                            <>
                                <div className="user-menu-backdrop" onClick={() => setShowUserMenu(false)} />
                                <div className="user-menu-dropdown">
                                    <div className="user-menu-info">
                                        <strong>{user?.display_name || 'User'}</strong>
                                        <span>{user?.email}</span>
                                    </div>
                                    <button
                                        className="user-menu-item"
                                        onClick={() => { onProfileClick?.(); setShowUserMenu(false); }}
                                    >
                                        <Icons.User size={14} />
                                        My Profile
                                    </button>
                                    {!showLogoutConfirm ? (
                                        <button
                                            className="user-menu-item user-menu-signout"
                                            onClick={() => setShowLogoutConfirm(true)}
                                        >
                                            <Icons.Logout size={14} />
                                            Sign Out
                                        </button>
                                    ) : (
                                        <div className="user-menu-logout-confirm">
                                            <p>Sign out?</p>
                                            <div className="user-menu-logout-btns">
                                                <button
                                                    className="btn btn-sm user-menu-logout-yes"
                                                    onClick={() => { logout(); setShowUserMenu(false); setShowLogoutConfirm(false); }}
                                                >
                                                    Yes
                                                </button>
                                                <button
                                                    className="btn btn-sm"
                                                    onClick={() => setShowLogoutConfirm(false)}
                                                >
                                                    No
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                ) : (
                    <button className="btn btn-primary btn-sm header-login-btn" onClick={onAuthClick}>
                        <Icons.Login size={14} />
                        Sign In
                    </button>
                )}
            </nav>
        </header>
    );
}

function App() {
    const [videos, setVideos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('all');
    const [showAuthModal, setShowAuthModal] = useState(false);
    const [showProfileModal, setShowProfileModal] = useState(false);
    const [showFavorites, setShowFavorites] = useState(false);
    const [favoriteIds, setFavoriteIds] = useState(new Set());
    const { isAuthenticated } = useAuth();
    const [theme, setTheme] = useState(() => {
        const saved = localStorage.getItem('theme');
        if (saved) return saved;
        return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    });
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

    // Fetch favorites when authenticated
    useEffect(() => {
        if (isAuthenticated) {
            fetchFavorites();
        } else {
            setFavoriteIds(new Set());
            setShowFavorites(false);
        }
    }, [isAuthenticated]);

    const fetchFavorites = async () => {
        try {
            const data = await getFavorites();
            setFavoriteIds(new Set(data.favorites || []));
        } catch (err) {
            console.error('Failed to fetch favorites:', err);
        }
    };

    const onFavoriteToggle = (videoId, isFavorited) => {
        setFavoriteIds(prev => {
            const next = new Set(prev);
            if (isFavorited) next.add(videoId);
            else next.delete(videoId);
            return next;
        });
    };

    const fetchVideos = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await getVideos();
            setVideos(data.videos || []);
        } catch (err) {
            console.error('Failed to fetch videos:', err);
            setError('Failed to load discourses. Please check your connection and try again.');
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
        const matchesFavorites = !showFavorites || favoriteIds.has(video.id);
        return matchesSearch && matchesCategory && matchesFavorites;
    });

    const headerProps = {
        theme, isThemeTransitioning, toggleTheme,
        onAuthClick: () => setShowAuthModal(true),
        onProfileClick: () => setShowProfileModal(true),
        onFavoritesClick: () => setShowFavorites(prev => !prev),
        showFavorites,
    };

    return (
        <div className={`app ${isThemeTransitioning ? 'theme-transitioning' : ''}`}>
            <AppHeader {...headerProps} />
            <Routes>
                <Route path="/video/:videoId" element={<VideoDetailPage />} />
                <Route path="*" element={
                    <HomePage
                        videos={filteredVideos}
                        loading={loading}
                        error={error}
                        searchQuery={searchQuery}
                        setSearchQuery={setSearchQuery}
                        categories={categories}
                        selectedCategory={selectedCategory}
                        setSelectedCategory={setSelectedCategory}
                        onRetry={fetchVideos}
                        favoriteIds={favoriteIds}
                        onFavoriteToggle={onFavoriteToggle}
                        showFavorites={showFavorites}
                    />
                } />
            </Routes>
            <footer className="footer">
                <p><span className="footer-brand">Divya Vaani AI</span> — Spiritual wisdom, powered by artificial intelligence</p>
            </footer>
            {showAuthModal && <AuthPage onClose={() => setShowAuthModal(false)} />}
            {showProfileModal && <Profile onClose={() => setShowProfileModal(false)} />}
        </div>
    );
}

/* Video detail page wrapper using URL params */
function VideoDetailPage() {
    const { videoId } = useParams();
    const navigate = useNavigate();
    return (
        <main className="main-detail">
            <VideoDetail videoId={videoId} onBack={() => navigate('/')} />
        </main>
    );
}

/* Home page with video grid */
const VIDEOS_PER_PAGE = 12;

function HomePage({ videos, loading, error, searchQuery, setSearchQuery, categories, selectedCategory, setSelectedCategory, onRetry, favoriteIds, onFavoriteToggle, showFavorites }) {
    const navigate = useNavigate();
    const [visibleCount, setVisibleCount] = useState(VIDEOS_PER_PAGE);
    const handleVideoClick = (video) => navigate(`/video/${video.id}`);

    // Reset visible count when filters change
    useEffect(() => { setVisibleCount(VIDEOS_PER_PAGE); }, [searchQuery, selectedCategory]);

    const visibleVideos = videos.slice(0, visibleCount);
    const hasMore = visibleCount < videos.length;

    return (
        <>
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
                            aria-label="Search discourses"
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
                ) : error ? (
                    <div className="empty-container">
                        <Icons.Close size={48} />
                        <h2>Something went wrong</h2>
                        <p>{error}</p>
                        <button className="btn btn-primary" onClick={onRetry}>
                            Try Again
                        </button>
                    </div>
                ) : videos.length === 0 ? (
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
                                {showFavorites ? `${videos.length} Favorite${videos.length !== 1 ? 's' : ''}` :
                                    `${videos.length} ${videos.length === 1 ? 'Discourse' : 'Discourses'}${selectedCategory !== 'all' ? ` in ${selectedCategory}` : ''}`
                                }
                            </h2>
                        </div>
                        <div className="videos-grid">
                            {visibleVideos.map(video => (
                                <VideoCard
                                    key={video.id}
                                    video={video}
                                    onClick={handleVideoClick}
                                    isFavorited={favoriteIds?.has(video.id)}
                                    onFavoriteToggle={onFavoriteToggle}
                                />
                            ))}
                        </div>
                        {hasMore && (
                            <div style={{ textAlign: 'center', padding: 'var(--space-6) 0' }}>
                                <button className="btn btn-primary" onClick={() => setVisibleCount(c => c + VIDEOS_PER_PAGE)}>
                                    Load More ({videos.length - visibleCount} remaining)
                                </button>
                            </div>
                        )}
                    </>
                )}
            </main>
        </>
    );
}

export default App;

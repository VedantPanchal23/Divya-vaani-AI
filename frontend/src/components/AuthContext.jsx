/**
 * AuthContext — React context for user authentication.
 * Manages JWT tokens, login/register/logout, and token refresh.
 */
import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const AuthContext = createContext(null);

const TOKEN_KEY = 'dv_access_token';
const REFRESH_KEY = 'dv_refresh_token';
const USER_KEY = 'dv_user';

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => {
        try {
            const saved = localStorage.getItem(USER_KEY);
            return saved ? JSON.parse(saved) : null;
        } catch { return null; }
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const refreshTimerRef = useRef(null);

    // Persist user to localStorage
    useEffect(() => {
        if (user) {
            localStorage.setItem(USER_KEY, JSON.stringify(user));
        } else {
            localStorage.removeItem(USER_KEY);
        }
    }, [user]);

    // Get stored token
    const getToken = useCallback(() => localStorage.getItem(TOKEN_KEY), []);
    const getRefreshToken = useCallback(() => localStorage.getItem(REFRESH_KEY), []);

    // Save tokens
    const saveTokens = useCallback((accessToken, refreshToken) => {
        localStorage.setItem(TOKEN_KEY, accessToken);
        localStorage.setItem(REFRESH_KEY, refreshToken);
    }, []);

    // Clear everything on logout
    const clearAuth = useCallback(() => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        localStorage.removeItem(USER_KEY);
        setUser(null);
        setError(null);
        if (refreshTimerRef.current) {
            clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = null;
        }
    }, []);

    // Schedule token refresh (refresh 5 min before expiry)
    const scheduleRefresh = useCallback((accessToken) => {
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        try {
            const payload = JSON.parse(atob(accessToken.split('.')[1]));
            const expiresIn = (payload.exp * 1000) - Date.now();
            const refreshIn = Math.max(expiresIn - 5 * 60 * 1000, 30_000); // at least 30s
            refreshTimerRef.current = setTimeout(async () => {
                try {
                    await refreshTokens();
                } catch {
                    clearAuth();
                }
            }, refreshIn);
        } catch { /* invalid token structure */ }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Refresh tokens
    const refreshTokens = useCallback(async () => {
        const refresh = getRefreshToken();
        if (!refresh) throw new Error('No refresh token');

        const res = await fetch('/api/auth/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refresh }),
        });

        if (!res.ok) {
            clearAuth();
            throw new Error('Session expired');
        }

        const data = await res.json();
        saveTokens(data.access_token, data.refresh_token);
        setUser(data.user);
        scheduleRefresh(data.access_token);
        return data;
    }, [getRefreshToken, clearAuth, saveTokens, scheduleRefresh]);

    // Auto-refresh on mount if token exists
    useEffect(() => {
        const token = getToken();
        if (token) {
            scheduleRefresh(token);
        }
        return () => {
            if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // Register
    const register = useCallback(async (email, password, displayName = '') => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/auth/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, display_name: displayName }),
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || 'Registration failed');
            }

            saveTokens(data.access_token, data.refresh_token);
            setUser(data.user);
            scheduleRefresh(data.access_token);
            return data;
        } catch (err) {
            setError(err.message);
            throw err;
        } finally {
            setLoading(false);
        }
    }, [saveTokens, scheduleRefresh]);

    // Login
    const login = useCallback(async (email, password) => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });

            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || 'Login failed');
            }

            saveTokens(data.access_token, data.refresh_token);
            setUser(data.user);
            scheduleRefresh(data.access_token);
            return data;
        } catch (err) {
            setError(err.message);
            throw err;
        } finally {
            setLoading(false);
        }
    }, [saveTokens, scheduleRefresh]);

    // Logout
    const logout = useCallback(() => {
        clearAuth();
    }, [clearAuth]);

    // Update profile
    const updateProfile = useCallback(async (displayName) => {
        const token = getToken();
        if (!token) throw new Error('Not authenticated');

        const res = await fetch('/api/auth/me', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({ display_name: displayName }),
        });

        if (!res.ok) throw new Error('Failed to update profile');
        const data = await res.json();
        setUser(data);
        return data;
    }, [getToken]);

    const value = {
        user,
        loading,
        error,
        isAuthenticated: !!user,
        getToken,
        register,
        login,
        logout,
        updateProfile,
        refreshTokens,
        clearError: () => setError(null),
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}

export default AuthContext;

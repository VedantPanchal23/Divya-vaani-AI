/**
 * AuthPage — Login / Register form with toggle.
 * Beautiful, clean design matching the spiritual theme.
 */
import { useState } from 'react';
import { useAuth } from './AuthContext';
import { Icons } from './Icons';

function AuthPage({ onClose }) {
    const { login, register, loading, error, clearError } = useAuth();
    const [isRegister, setIsRegister] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [localError, setLocalError] = useState('');

    const switchMode = () => {
        setIsRegister(!isRegister);
        setLocalError('');
        clearError();
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLocalError('');
        clearError();

        if (!email.trim() || !password.trim()) {
            setLocalError('Please fill in all required fields.');
            return;
        }

        if (password.length < 6) {
            setLocalError('Password must be at least 6 characters.');
            return;
        }

        try {
            if (isRegister) {
                await register(email.trim(), password, displayName.trim());
            } else {
                await login(email.trim(), password);
            }
            onClose?.();
        } catch {
            // error is already set by AuthContext
        }
    };

    const errorMsg = localError || error;

    return (
        <div className="auth-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
            <div className="auth-modal">
                <button className="auth-close" onClick={onClose} title="Close">
                    <Icons.Close size={20} />
                </button>

                <div className="auth-header">
                    <Icons.Spiritual size={32} />
                    <h2>{isRegister ? 'Create Account' : 'Welcome Back'}</h2>
                    <p className="auth-subtitle">
                        {isRegister
                            ? 'Join Divya Vaani AI to save favorites and chat history'
                            : 'Sign in to access your saved content'}
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="auth-form">
                    {isRegister && (
                        <div className="auth-field">
                            <label htmlFor="auth-name">Display Name</label>
                            <input
                                id="auth-name"
                                type="text"
                                placeholder="Your name (optional)"
                                value={displayName}
                                onChange={(e) => setDisplayName(e.target.value)}
                                maxLength={100}
                                autoComplete="name"
                            />
                        </div>
                    )}

                    <div className="auth-field">
                        <label htmlFor="auth-email">Email *</label>
                        <input
                            id="auth-email"
                            type="email"
                            placeholder="you@example.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            autoComplete="email"
                            autoFocus
                        />
                    </div>

                    <div className="auth-field">
                        <label htmlFor="auth-password">Password *</label>
                        <input
                            id="auth-password"
                            type="password"
                            placeholder={isRegister ? 'Min 6 characters' : 'Your password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            minLength={6}
                            autoComplete={isRegister ? 'new-password' : 'current-password'}
                        />
                    </div>

                    {errorMsg && (
                        <div className="auth-error">
                            <Icons.Error size={14} />
                            {errorMsg}
                        </div>
                    )}

                    <button type="submit" className="btn btn-primary auth-submit" disabled={loading}>
                        {loading ? (
                            <>
                                <Icons.Loading size={16} className="animate-spin" />
                                {isRegister ? 'Creating...' : 'Signing in...'}
                            </>
                        ) : (
                            isRegister ? 'Create Account' : 'Sign In'
                        )}
                    </button>
                </form>

                <div className="auth-footer">
                    <span>
                        {isRegister ? 'Already have an account?' : "Don't have an account?"}
                    </span>
                    <button className="auth-switch" onClick={switchMode}>
                        {isRegister ? 'Sign In' : 'Create Account'}
                    </button>
                </div>
            </div>
        </div>
    );
}

export default AuthPage;

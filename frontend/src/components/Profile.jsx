/**
 * Profile — User profile page/modal with account info, 
 * display name editing, and account management.
 */
import { useState } from 'react';
import { useAuth } from './AuthContext';
import { Icons } from './Icons';

function Profile({ onClose }) {
    const { user, updateProfile, logout, loading } = useAuth();
    const [isEditing, setIsEditing] = useState(false);
    const [displayName, setDisplayName] = useState(user?.display_name || '');
    const [saveStatus, setSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

    const handleSave = async () => {
        if (!displayName.trim()) return;
        setSaveStatus('saving');
        try {
            await updateProfile(displayName.trim());
            setSaveStatus('saved');
            setIsEditing(false);
            setTimeout(() => setSaveStatus(null), 2000);
        } catch {
            setSaveStatus('error');
            setTimeout(() => setSaveStatus(null), 3000);
        }
    };

    const handleLogout = () => {
        logout();
        onClose?.();
    };

    const memberSince = user?.created_at
        ? new Date(user.created_at).toLocaleDateString('en-IN', {
            year: 'numeric', month: 'long', day: 'numeric'
        })
        : 'Unknown';

    return (
        <div className="auth-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
            <div className="auth-modal profile-modal">
                <button className="auth-close" onClick={onClose} title="Close">
                    <Icons.Close size={20} />
                </button>

                <div className="auth-header">
                    <div className="profile-avatar">
                        <Icons.User size={32} />
                    </div>
                    <h2>My Profile</h2>
                    <p className="auth-subtitle">Manage your account settings</p>
                </div>

                <div className="profile-content">
                    {/* Display Name */}
                    <div className="profile-field">
                        <label>Display Name</label>
                        {isEditing ? (
                            <div className="profile-edit-row">
                                <input
                                    type="text"
                                    value={displayName}
                                    onChange={(e) => setDisplayName(e.target.value)}
                                    placeholder="Enter display name"
                                    maxLength={100}
                                    autoFocus
                                    className="profile-input"
                                />
                                <button
                                    className="btn btn-primary btn-sm"
                                    onClick={handleSave}
                                    disabled={saveStatus === 'saving' || !displayName.trim()}
                                >
                                    {saveStatus === 'saving' ? (
                                        <Icons.Loading size={14} className="animate-spin" />
                                    ) : 'Save'}
                                </button>
                                <button
                                    className="btn btn-sm profile-cancel-btn"
                                    onClick={() => { setIsEditing(false); setDisplayName(user?.display_name || ''); }}
                                >
                                    Cancel
                                </button>
                            </div>
                        ) : (
                            <div className="profile-value-row">
                                <span className="profile-value">
                                    {user?.display_name || <em className="profile-not-set">Not set</em>}
                                </span>
                                <button
                                    className="profile-edit-btn"
                                    onClick={() => setIsEditing(true)}
                                    title="Edit name"
                                >
                                    <Icons.Settings size={14} />
                                </button>
                            </div>
                        )}
                        {saveStatus === 'saved' && (
                            <span className="profile-save-status success">
                                <Icons.Success size={12} /> Saved!
                            </span>
                        )}
                        {saveStatus === 'error' && (
                            <span className="profile-save-status error">
                                <Icons.Error size={12} /> Failed to save
                            </span>
                        )}
                    </div>

                    {/* Email */}
                    <div className="profile-field">
                        <label>Email</label>
                        <span className="profile-value">{user?.email || 'Unknown'}</span>
                    </div>

                    {/* Member Since */}
                    <div className="profile-field">
                        <label>Member Since</label>
                        <span className="profile-value">{memberSince}</span>
                    </div>
                </div>

                {/* Actions */}
                <div className="profile-actions">
                    {showLogoutConfirm ? (
                        <div className="profile-logout-confirm">
                            <p>Are you sure you want to sign out?</p>
                            <div className="profile-logout-btns">
                                <button
                                    className="btn btn-sm profile-logout-yes"
                                    onClick={handleLogout}
                                >
                                    Yes, Sign Out
                                </button>
                                <button
                                    className="btn btn-sm"
                                    onClick={() => setShowLogoutConfirm(false)}
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    ) : (
                        <button
                            className="profile-signout-btn"
                            onClick={() => setShowLogoutConfirm(true)}
                        >
                            <Icons.Logout size={16} />
                            Sign Out
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

export default Profile;

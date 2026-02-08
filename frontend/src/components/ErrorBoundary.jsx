import { Component } from 'react';

class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('App error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minHeight: '100vh',
                    padding: '2rem',
                    textAlign: 'center',
                    fontFamily: 'system-ui, sans-serif'
                }}>
                    <h1 style={{ fontSize: '2rem', marginBottom: '1rem' }}>
                        🙏 Something went wrong
                    </h1>
                    <p style={{ color: '#666', marginBottom: '1.5rem', maxWidth: '500px' }}>
                        An unexpected error occurred. Please refresh the page to try again.
                    </p>
                    <button
                        onClick={() => window.location.reload()}
                        style={{
                            padding: '0.75rem 2rem',
                            fontSize: '1rem',
                            borderRadius: '8px',
                            border: 'none',
                            backgroundColor: '#e67e22',
                            color: 'white',
                            cursor: 'pointer'
                        }}
                    >
                        Refresh Page
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;

import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
  isChunkError: boolean;
}

/**
 * Check if error is a chunk loading failure (common after deployments)
 */
function isChunkLoadError(error: Error): boolean {
  const message = error.message || '';
  return (
    message.includes('Failed to fetch dynamically imported module') ||
    message.includes('Loading chunk') ||
    message.includes('Loading CSS chunk') ||
    message.includes('ChunkLoadError') ||
    // Vite specific error messages
    message.includes('Unable to preload CSS') ||
    message.includes('Failed to load module script')
  );
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, isChunkError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    const isChunkError = isChunkLoadError(error);
    return { hasError: true, error, isChunkError };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error details to console in development
    console.error('ErrorBoundary caught an error:', error, errorInfo);

    const isChunkError = isChunkLoadError(error);

    // Update state with error details
    this.setState({
      error,
      errorInfo,
      isChunkError
    });

    // Auto-reload on chunk errors (deployment caused stale cache)
    if (isChunkError) {
      // Check if we already tried to reload recently (prevent infinite loop)
      const lastReload = sessionStorage.getItem('chunk-error-reload');
      const now = Date.now();

      if (!lastReload || now - parseInt(lastReload) > 10000) {
        // Set flag and reload after short delay
        sessionStorage.setItem('chunk-error-reload', now.toString());
        console.log('Chunk load error detected, reloading page...');
        setTimeout(() => {
          window.location.reload();
        }, 500);
      }
    }

    // In production, you could send this to an error reporting service
    // Example: logErrorToService(error, errorInfo);
  }

  handleReload = () => {
    // Clear error state and force reload (bypass cache)
    window.location.reload();
  };

  handleHardReload = () => {
    // Clear caches and force reload
    if ('caches' in window) {
      caches.keys().then(names => {
        names.forEach(name => caches.delete(name));
      });
    }
    // Clear session storage flag
    sessionStorage.removeItem('chunk-error-reload');
    // Force reload from server
    window.location.href = window.location.href;
  };

  handleReset = () => {
    // Clear error state and try to recover
    this.setState({ hasError: false, error: undefined, errorInfo: undefined, isChunkError: false });
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback UI from props
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-dark-900 via-dark-800 to-dark-900 p-4">
          <div className="max-w-2xl w-full bg-dark-800/50 backdrop-blur-sm border border-white/10 rounded-lg p-8 shadow-xl">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-red-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Something went wrong</h1>
                <p className="text-sm text-gray-400">
                  The application encountered an unexpected error
                </p>
              </div>
            </div>

            {this.state.error && (
              <div className="mb-6 p-4 bg-dark-900/50 rounded border border-red-500/20">
                <p className="text-sm font-mono text-red-400 mb-2">
                  {this.state.error.toString()}
                </p>
                {this.state.errorInfo && (
                  <details className="mt-2">
                    <summary className="text-sm text-gray-400 cursor-pointer hover:text-gray-300">
                      Stack trace
                    </summary>
                    <pre className="mt-2 text-xs text-gray-500 overflow-auto max-h-48">
                      {this.state.errorInfo.componentStack}
                    </pre>
                  </details>
                )}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={this.handleReload}
                className="flex-1 px-4 py-2 bg-accent-500 hover:bg-accent-600 text-white rounded-lg font-medium transition-colors"
              >
                Reload Page
              </button>
              {this.state.isChunkError ? (
                <button
                  onClick={this.handleHardReload}
                  className="flex-1 px-4 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors border border-white/10"
                >
                  Clear Cache & Reload
                </button>
              ) : (
                <button
                  onClick={this.handleReset}
                  className="flex-1 px-4 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors border border-white/10"
                >
                  Try Again
                </button>
              )}
            </div>

            <p className="mt-4 text-xs text-gray-500 text-center">
              {this.state.isChunkError
                ? 'This usually happens after an app update. Reloading should fix it.'
                : 'If this problem persists, please contact support'}
            </p>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;

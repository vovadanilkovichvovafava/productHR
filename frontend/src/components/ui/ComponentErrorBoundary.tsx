import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  componentName?: string;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error?: Error;
}

/**
 * A lightweight error boundary for individual components.
 * Use this to isolate errors in specific parts of the UI without crashing the entire app.
 *
 * @example
 * <ComponentErrorBoundary componentName="ChatList">
 *   <ChatList chats={chats} />
 * </ComponentErrorBoundary>
 */
class ComponentErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error for development
    console.error(`[${this.props.componentName || 'Component'}] Error:`, error, errorInfo);

    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default compact error UI
      return (
        <div
          className="flex flex-col items-center justify-center p-6 bg-red-500/5 border border-red-500/20 rounded-lg"
          role="alert"
          aria-live="assertive"
        >
          <AlertTriangle className="w-8 h-8 text-red-400 mb-2" aria-hidden="true" />
          <p className="text-sm text-red-400 mb-3">
            {this.props.componentName
              ? `${this.props.componentName} failed to load`
              : 'Failed to load component'}
          </p>
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-2 px-3 py-1.5 text-xs bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded transition-colors"
            aria-label="Retry loading component"
          >
            <RefreshCw className="w-3 h-3" aria-hidden="true" />
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ComponentErrorBoundary;

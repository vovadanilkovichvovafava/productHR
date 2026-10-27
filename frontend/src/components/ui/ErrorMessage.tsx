import { AlertCircle, WifiOff, ShieldOff, FileQuestion, ServerCrash, RefreshCw } from 'lucide-react';
import clsx from 'clsx';

export type ErrorType = 'network' | 'forbidden' | 'not_found' | 'server' | 'unknown';

export interface ErrorMessageProps {
  error: string | Error | null;
  errorType?: ErrorType;
  onRetry?: () => void;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

interface ErrorConfig {
  icon: typeof AlertCircle;
  title: string;
  message: string;
  iconColor: string;
}

/**
 * Get the error type from an error object or status code
 */
export function getErrorType(error: unknown): ErrorType {
  if (!error) return 'unknown';

  const errorMessage = error instanceof Error ? error.message : String(error);
  const lowerMessage = errorMessage.toLowerCase();

  // Check for network errors
  if (
    lowerMessage.includes('network') ||
    lowerMessage.includes('failed to fetch') ||
    lowerMessage.includes('connection') ||
    lowerMessage.includes('timeout') ||
    lowerMessage.includes('offline')
  ) {
    return 'network';
  }

  // Check for status codes in error message
  if (lowerMessage.includes('403') || lowerMessage.includes('forbidden')) {
    return 'forbidden';
  }

  if (lowerMessage.includes('404') || lowerMessage.includes('not found')) {
    return 'not_found';
  }

  if (
    lowerMessage.includes('500') ||
    lowerMessage.includes('502') ||
    lowerMessage.includes('503') ||
    lowerMessage.includes('server error')
  ) {
    return 'server';
  }

  return 'unknown';
}

/**
 * Get the error type from an HTTP status code
 */
export function getErrorTypeFromStatus(status: number): ErrorType {
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status >= 500) return 'server';
  return 'unknown';
}

const errorConfigs: Record<ErrorType, ErrorConfig> = {
  network: {
    icon: WifiOff,
    title: 'Connection Failed',
    message: 'Check your internet connection and try again.',
    iconColor: 'text-orange-400',
  },
  forbidden: {
    icon: ShieldOff,
    title: 'Access Denied',
    message: "You don't have permission to access this resource.",
    iconColor: 'text-red-400',
  },
  not_found: {
    icon: FileQuestion,
    title: 'Not Found',
    message: 'The requested resource could not be found.',
    iconColor: 'text-yellow-400',
  },
  server: {
    icon: ServerCrash,
    title: 'Server Error',
    message: 'Something went wrong on our end. Please try again later.',
    iconColor: 'text-red-400',
  },
  unknown: {
    icon: AlertCircle,
    title: 'Something Went Wrong',
    message: 'An unexpected error occurred. Please try again.',
    iconColor: 'text-red-400',
  },
};

const sizeStyles = {
  sm: {
    container: 'py-6 px-4',
    icon: 'w-10 h-10',
    title: 'text-base',
    message: 'text-sm',
    button: 'px-3 py-1.5 text-sm',
  },
  md: {
    container: 'py-10 px-6',
    icon: 'w-14 h-14',
    title: 'text-lg',
    message: 'text-sm',
    button: 'px-4 py-2',
  },
  lg: {
    container: 'py-16 px-8',
    icon: 'w-20 h-20',
    title: 'text-xl',
    message: 'text-base',
    button: 'px-5 py-2.5',
  },
};

export default function ErrorMessage({
  error,
  errorType,
  onRetry,
  className,
  size = 'md',
}: ErrorMessageProps) {
  if (!error) return null;

  const detectedType = errorType || getErrorType(error);
  const config = errorConfigs[detectedType];
  const Icon = config.icon;
  const styles = sizeStyles[size];

  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center text-center',
        styles.container,
        className
      )}
      role="alert"
    >
      <div className="p-4 glass-light rounded-full mb-4">
        <Icon className={clsx(styles.icon, config.iconColor)} aria-hidden="true" />
      </div>
      <h3 className={clsx('font-semibold text-white', styles.title)}>
        {config.title}
      </h3>
      <p className={clsx('text-white/60 mt-2 max-w-md', styles.message)}>
        {config.message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className={clsx(
            'mt-4 flex items-center gap-2 bg-blue-600 hover:bg-blue-500 rounded-lg transition-colors',
            styles.button
          )}
          aria-label="Попробовать снова"
        >
          <RefreshCw className="w-4 h-4" aria-hidden="true" />
          Try Again
        </button>
      )}
    </div>
  );
}

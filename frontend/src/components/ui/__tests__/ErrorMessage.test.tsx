import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorMessage, { getErrorType, getErrorTypeFromStatus } from '../ErrorMessage';

describe('ErrorMessage', () => {
  it('should render nothing when error is null', () => {
    const { container } = render(<ErrorMessage error={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('should render error message when error is provided', () => {
    render(<ErrorMessage error="Something went wrong" />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Something Went Wrong')).toBeInTheDocument();
  });

  it('should render retry button when onRetry is provided', () => {
    const onRetry = vi.fn();
    render(<ErrorMessage error="Error" onRetry={onRetry} />);

    const retryButton = screen.getByText('Try Again');
    expect(retryButton).toBeInTheDocument();

    fireEvent.click(retryButton);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('should not render retry button when onRetry is not provided', () => {
    render(<ErrorMessage error="Error" />);
    expect(screen.queryByText('Try Again')).not.toBeInTheDocument();
  });

  describe('error type detection', () => {
    it('should detect network errors', () => {
      render(<ErrorMessage error="Network error" />);
      expect(screen.getByText('Connection Failed')).toBeInTheDocument();
    });

    it('should detect failed to fetch errors', () => {
      render(<ErrorMessage error="Failed to fetch" />);
      expect(screen.getByText('Connection Failed')).toBeInTheDocument();
    });

    it('should detect connection errors', () => {
      render(<ErrorMessage error="Connection refused" />);
      expect(screen.getByText('Connection Failed')).toBeInTheDocument();
    });

    it('should detect 403 forbidden errors', () => {
      render(<ErrorMessage error="403 Forbidden" />);
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });

    it('should detect 404 not found errors', () => {
      render(<ErrorMessage error="404 Not Found" />);
      expect(screen.getByText('Not Found')).toBeInTheDocument();
    });

    it('should detect 500 server errors', () => {
      render(<ErrorMessage error="500 Internal Server Error" />);
      expect(screen.getByText('Server Error')).toBeInTheDocument();
    });

    it('should use explicit errorType when provided', () => {
      render(<ErrorMessage error="Generic error" errorType="forbidden" />);
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });
  });

  describe('size variants', () => {
    it('should render small size correctly', () => {
      render(<ErrorMessage error="Error" size="sm" />);
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('should render medium size correctly (default)', () => {
      render(<ErrorMessage error="Error" />);
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('should render large size correctly', () => {
      render(<ErrorMessage error="Error" size="lg" />);
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  it('should apply custom className', () => {
    render(<ErrorMessage error="Error" className="custom-class" />);
    expect(screen.getByRole('alert')).toHaveClass('custom-class');
  });

  it('should handle Error objects', () => {
    render(<ErrorMessage error={new Error('Test error message')} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

describe('getErrorType helper', () => {
  it('should return unknown for null/undefined', () => {
    expect(getErrorType(null)).toBe('unknown');
    expect(getErrorType(undefined)).toBe('unknown');
  });

  it('should detect network errors', () => {
    expect(getErrorType('network error')).toBe('network');
    expect(getErrorType('Failed to fetch')).toBe('network');
    expect(getErrorType('Connection timeout')).toBe('network');
    expect(getErrorType('offline')).toBe('network');
  });

  it('should detect forbidden errors', () => {
    expect(getErrorType('403 forbidden')).toBe('forbidden');
    expect(getErrorType('Error: 403')).toBe('forbidden');
  });

  it('should detect not found errors', () => {
    expect(getErrorType('404 not found')).toBe('not_found');
    expect(getErrorType('Resource not found')).toBe('not_found');
  });

  it('should detect server errors', () => {
    expect(getErrorType('500 Internal Server Error')).toBe('server');
    expect(getErrorType('502 Bad Gateway')).toBe('server');
    expect(getErrorType('503 Service Unavailable')).toBe('server');
    expect(getErrorType('server error')).toBe('server');
  });

  it('should return unknown for unrecognized errors', () => {
    expect(getErrorType('Something happened')).toBe('unknown');
    expect(getErrorType('Validation failed')).toBe('unknown');
  });

  it('should handle Error objects', () => {
    expect(getErrorType(new Error('network error'))).toBe('network');
    expect(getErrorType(new Error('403 forbidden'))).toBe('forbidden');
  });
});

describe('getErrorTypeFromStatus helper', () => {
  it('should return forbidden for 403', () => {
    expect(getErrorTypeFromStatus(403)).toBe('forbidden');
  });

  it('should return not_found for 404', () => {
    expect(getErrorTypeFromStatus(404)).toBe('not_found');
  });

  it('should return server for 5xx errors', () => {
    expect(getErrorTypeFromStatus(500)).toBe('server');
    expect(getErrorTypeFromStatus(502)).toBe('server');
    expect(getErrorTypeFromStatus(503)).toBe('server');
  });

  it('should return unknown for other status codes', () => {
    expect(getErrorTypeFromStatus(400)).toBe('unknown');
    expect(getErrorTypeFromStatus(401)).toBe('unknown');
    expect(getErrorTypeFromStatus(200)).toBe('unknown');
  });
});

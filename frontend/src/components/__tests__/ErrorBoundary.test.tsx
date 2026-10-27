import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorBoundary from '../ErrorBoundary';

// Component that throws an error when flag is set
const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>No error</div>;
};

describe('ErrorBoundary', () => {
  // Suppress console.error in tests to avoid cluttering test output
  const originalError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalError;
  });

  it('should render children when there is no error', () => {
    render(
      <ErrorBoundary>
        <div>Test content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('Test content')).toBeInTheDocument();
  });

  it('should catch errors and display default fallback UI', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    // Check that error UI is displayed
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(
      screen.getByText('The application encountered an unexpected error')
    ).toBeInTheDocument();

    // Check that error message is displayed
    expect(screen.getByText(/Test error/)).toBeInTheDocument();

    // Check that action buttons are rendered
    expect(screen.getByText('Reload Page')).toBeInTheDocument();
    expect(screen.getByText('Try Again')).toBeInTheDocument();
  });

  it('should display custom fallback when provided', () => {
    const customFallback = <div>Custom error message</div>;

    render(
      <ErrorBoundary fallback={customFallback}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom error message')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('should reload page when Reload button is clicked', () => {
    // Mock window.location.reload
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
    });

    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    const reloadButton = screen.getByText('Reload Page');
    fireEvent.click(reloadButton);

    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it('should attempt to recover when Try Again is clicked', () => {
    // Use a component that can toggle error state
    let shouldThrow = true;
    const ErrorToggle = () => {
      if (shouldThrow) {
        throw new Error('Test error');
      }
      return <div>Recovered successfully</div>;
    };

    const { rerender } = render(
      <ErrorBoundary>
        <ErrorToggle />
      </ErrorBoundary>
    );

    // Error UI should be visible
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Disable error before clicking Try Again
    shouldThrow = false;

    // Click Try Again button to reset error state
    const tryAgainButton = screen.getByText('Try Again');
    fireEvent.click(tryAgainButton);

    // After clicking Try Again, the boundary should attempt to re-render
    // Since shouldThrow is now false, it should render successfully
    expect(screen.getByText('Recovered successfully')).toBeInTheDocument();
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  });

  it('should log error to console when error occurs', () => {
    const consoleErrorSpy = vi.spyOn(console, 'error');

    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    // Verify that console.error was called (React logs errors to console)
    expect(consoleErrorSpy).toHaveBeenCalled();

    // Check that our custom error logging was called
    // We expect to find our custom error message in one of the console.error calls
    const customErrorCall = consoleErrorSpy.mock.calls.find(
      (call) => typeof call[0] === 'string' && call[0].includes('ErrorBoundary caught an error:')
    );
    expect(customErrorCall).toBeDefined();
  });

  it('should display stack trace in details element', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    // Stack trace should be in a details element
    const stackTraceToggle = screen.getByText('Stack trace');
    expect(stackTraceToggle).toBeInTheDocument();

    // Click to expand details
    fireEvent.click(stackTraceToggle);

    // Component stack should be visible
    const detailsElement = stackTraceToggle.closest('details');
    expect(detailsElement).toHaveAttribute('open');
  });
});

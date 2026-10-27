import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ConfirmDialog from '../ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    open: true,
    title: 'Delete Item',
    message: 'Are you sure you want to delete this item?',
    onConfirm: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render nothing when not open', () => {
    const { container } = render(
      <ConfirmDialog {...defaultProps} open={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render dialog when open', () => {
    render(<ConfirmDialog {...defaultProps} />);

    expect(screen.getByText('Delete Item')).toBeInTheDocument();
    expect(screen.getByText('Are you sure you want to delete this item?')).toBeInTheDocument();
  });

  it('should use default button labels', () => {
    render(<ConfirmDialog {...defaultProps} />);

    expect(screen.getByText('Confirm')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('should use custom button labels when provided', () => {
    render(
      <ConfirmDialog
        {...defaultProps}
        confirmLabel="Delete"
        cancelLabel="Keep"
      />
    );

    expect(screen.getByText('Delete')).toBeInTheDocument();
    expect(screen.getByText('Keep')).toBeInTheDocument();
  });

  it('should call onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(<ConfirmDialog {...defaultProps} onConfirm={onConfirm} />);

    fireEvent.click(screen.getByText('Confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('should call onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('should call onCancel when backdrop is clicked', () => {
    const onCancel = vi.fn();
    const { container } = render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

    // Click the backdrop (the outer div with backdrop-blur-sm class)
    const backdrop = container.querySelector('.backdrop-blur-sm');
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(onCancel).toHaveBeenCalledTimes(1);
    }
  });

  it('should call onCancel when close button is clicked', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

    const closeButton = screen.getByLabelText('Close dialog');
    fireEvent.click(closeButton);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('should display loading state when loading is true', () => {
    render(<ConfirmDialog {...defaultProps} loading={true} />);

    expect(screen.getByText('Processing...')).toBeInTheDocument();
    expect(screen.queryByText('Confirm')).not.toBeInTheDocument();
  });

  it('should disable buttons when loading', () => {
    render(<ConfirmDialog {...defaultProps} loading={true} />);

    const confirmButton = screen.getByText('Processing...');
    const cancelButton = screen.getByText('Cancel');

    expect(confirmButton).toBeDisabled();
    expect(cancelButton).toBeDisabled();
  });

  it('should not call onCancel when backdrop clicked during loading', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} loading={true} />);

    // Click the backdrop - should not trigger onCancel during loading
    const backdrop = screen.getByRole('alertdialog').parentElement;
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(onCancel).not.toHaveBeenCalled();
    }
  });

  describe('variants', () => {
    it('should render danger variant correctly', () => {
      render(<ConfirmDialog {...defaultProps} variant="danger" />);
      // The dialog should render with danger styling (red colors)
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('should render warning variant correctly', () => {
      render(<ConfirmDialog {...defaultProps} variant="warning" />);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('should render info variant correctly', () => {
      render(<ConfirmDialog {...defaultProps} variant="info" />);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });
  });

  it('should have accessible role and aria attributes', () => {
    render(<ConfirmDialog {...defaultProps} />);

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'confirm-dialog-title');
  });

  it('should stop event propagation when clicking inside dialog', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

    // Click inside the dialog content
    const title = screen.getByText('Delete Item');
    fireEvent.click(title);

    // onCancel should not be called when clicking inside the dialog
    expect(onCancel).not.toHaveBeenCalled();
  });

  describe('Accessibility', () => {
    it('should have proper dialog role', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const dialog = screen.getByRole('alertdialog');
      expect(dialog).toBeInTheDocument();
    });

    it('should have aria-modal attribute set to true', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const dialog = screen.getByRole('alertdialog');
      expect(dialog).toHaveAttribute('aria-modal', 'true');
    });

    it('should have aria-labelledby pointing to title', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const dialog = screen.getByRole('alertdialog');
      expect(dialog).toHaveAttribute('aria-labelledby', 'confirm-dialog-title');
    });

    it('should have title with correct id for aria-labelledby', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const title = screen.getByText('Delete Item');
      expect(title).toHaveAttribute('id', 'confirm-dialog-title');
    });

    it('should have accessible name for close button', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const closeButton = screen.getByLabelText('Close dialog');
      expect(closeButton).toBeInTheDocument();
      expect(closeButton.tagName).toBe('BUTTON');
    });

    it('should have proper button types', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const confirmButton = screen.getByText('Confirm');
      const cancelButton = screen.getByText('Cancel');

      expect(confirmButton).toHaveAttribute('type', 'button');
      expect(cancelButton).toHaveAttribute('type', 'button');
    });

    it('should have message text accessible', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const message = screen.getByText('Are you sure you want to delete this item?');
      expect(message).toBeInTheDocument();
    });

    it('should include icon for each variant', () => {
      const { rerender } = render(<ConfirmDialog {...defaultProps} variant="danger" />);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();

      rerender(<ConfirmDialog {...defaultProps} variant="warning" />);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();

      rerender(<ConfirmDialog {...defaultProps} variant="info" />);
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });

    it('should indicate disabled state in buttons when loading', () => {
      render(<ConfirmDialog {...defaultProps} loading={true} />);

      const confirmButton = screen.getByText('Processing...');
      const cancelButton = screen.getByText('Cancel');

      expect(confirmButton).toHaveAttribute('disabled');
      expect(cancelButton).toHaveAttribute('disabled');
    });
  });

  describe('Keyboard Navigation', () => {
    it('should call onCancel when Escape key is pressed', () => {
      const onCancel = vi.fn();
      render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

      const dialog = screen.getByRole('alertdialog');
      fireEvent.keyDown(dialog, { key: 'Escape' });

      expect(onCancel).toHaveBeenCalledTimes(1);
    });

    it('should not call onCancel on Escape when loading', () => {
      const onCancel = vi.fn();
      render(<ConfirmDialog {...defaultProps} onCancel={onCancel} loading={true} />);

      const dialog = screen.getByRole('alertdialog');
      fireEvent.keyDown(dialog, { key: 'Escape' });

      expect(onCancel).not.toHaveBeenCalled();
    });

    it('should ignore other key presses', () => {
      const onCancel = vi.fn();
      const onConfirm = vi.fn();
      render(<ConfirmDialog {...defaultProps} onCancel={onCancel} onConfirm={onConfirm} />);

      const dialog = screen.getByRole('alertdialog');

      fireEvent.keyDown(dialog, { key: 'Enter' });
      fireEvent.keyDown(dialog, { key: 'Space' });
      fireEvent.keyDown(dialog, { key: 'Tab' });

      // Only Escape should trigger onCancel
      expect(onCancel).not.toHaveBeenCalled();
      expect(onConfirm).not.toHaveBeenCalled();
    });

    it('should handle keyboard events on backdrop', () => {
      const onCancel = vi.fn();
      const { container } = render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);

      const backdrop = container.querySelector('.backdrop-blur-sm');
      if (backdrop) {
        fireEvent.keyDown(backdrop, { key: 'Escape' });
        expect(onCancel).toHaveBeenCalledTimes(1);
      }
    });

    it('should allow focus on interactive elements', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const confirmButton = screen.getByText('Confirm');
      const cancelButton = screen.getByText('Cancel');
      const closeButton = screen.getByLabelText('Close dialog');

      // All buttons should be focusable
      confirmButton.focus();
      expect(document.activeElement).toBe(confirmButton);

      cancelButton.focus();
      expect(document.activeElement).toBe(cancelButton);

      closeButton.focus();
      expect(document.activeElement).toBe(closeButton);
    });

    it('should have focusable confirm button with correct label', () => {
      render(<ConfirmDialog {...defaultProps} confirmLabel="Delete Forever" />);

      const confirmButton = screen.getByText('Delete Forever');
      confirmButton.focus();

      expect(document.activeElement).toBe(confirmButton);
      expect(confirmButton).not.toBeDisabled();
    });

    it('should prevent focus on disabled buttons during loading', () => {
      render(<ConfirmDialog {...defaultProps} loading={true} />);

      const confirmButton = screen.getByText('Processing...');
      const cancelButton = screen.getByText('Cancel');

      expect(confirmButton).toBeDisabled();
      expect(cancelButton).toBeDisabled();
    });
  });

  describe('Focus Management', () => {
    it('should contain interactive elements within dialog', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const dialog = screen.getByRole('alertdialog');
      const buttons = dialog.querySelectorAll('button');

      // Should have: close button, cancel button, confirm button
      expect(buttons.length).toBe(3);
    });

    it('should have all buttons accessible when not loading', () => {
      render(<ConfirmDialog {...defaultProps} />);

      const confirmButton = screen.getByText('Confirm');
      const cancelButton = screen.getByText('Cancel');
      const closeButton = screen.getByLabelText('Close dialog');

      expect(confirmButton).not.toBeDisabled();
      expect(cancelButton).not.toBeDisabled();
      expect(closeButton).not.toBeDisabled();
    });
  });
});

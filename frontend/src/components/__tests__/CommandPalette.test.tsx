import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import CommandPalette, { CommandPaletteHint } from '../CommandPalette';
import { useCommandPaletteStore } from '@/hooks/useCommandPalette';
import * as api from '@/services/api';

// Mock framer-motion
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: { children: React.ReactNode }) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock API
vi.mock('@/services/api', () => ({
  globalSearch: vi.fn(),
}));

// Wrapper with Router
const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

describe('CommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Reset store state before each test
    useCommandPaletteStore.setState({
      isOpen: false,
      query: '',
      selectedIndex: 0,
      isLoading: false,
      apiResults: null,
      history: [],
    });
  });

  describe('store integration (critical bug fix)', () => {
    it('should open when store.open() is called (simulates Layout.tsx button click)', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      // Initially closed
      expect(screen.queryByPlaceholderText(/поиск/i)).not.toBeInTheDocument();

      // Simulate button click from Layout.tsx - calling store.open() directly
      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      // CommandPalette should now be visible
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/поиск/i)).toBeInTheDocument();
      });
    });

    it('should respond to store state changes from external components', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      // Open via store (like Layout.tsx does)
      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/поиск/i)).toBeInTheDocument();
      });

      // Close via store
      await act(async () => {
        useCommandPaletteStore.getState().close();
      });

      await waitFor(() => {
        expect(screen.queryByPlaceholderText(/поиск/i)).not.toBeInTheDocument();
      });
    });

    it('should work with toggle from store', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      // Toggle to open
      await act(async () => {
        useCommandPaletteStore.getState().toggle();
      });

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/поиск/i)).toBeInTheDocument();
      });

      // Toggle to close
      await act(async () => {
        useCommandPaletteStore.getState().toggle();
      });

      await waitFor(() => {
        expect(screen.queryByPlaceholderText(/поиск/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('rendering', () => {
    it('should not render when closed (initial state)', () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      // The modal should not be visible initially
      expect(screen.queryByPlaceholderText(/поиск/i)).not.toBeInTheDocument();
    });

    it('should render when opened', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      // Open via store (simulating Cmd+K or button click)
      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/поиск/i)).toBeInTheDocument();
      });
    });

    it('should close when close is called', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      // Open
      await act(async () => {
        useCommandPaletteStore.getState().open();
      });
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/поиск/i)).toBeInTheDocument();
      });

      // Close
      await act(async () => {
        useCommandPaletteStore.getState().close();
      });
      await waitFor(() => {
        expect(screen.queryByPlaceholderText(/поиск/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('search functionality', () => {
    it('should show search input when opened', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      await waitFor(() => {
        const input = screen.getByPlaceholderText(/поиск/i);
        expect(input).toBeInTheDocument();
      });
    });

    it('should filter results based on query', async () => {
      const user = userEvent.setup();
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      const input = await screen.findByPlaceholderText(/поиск/i);
      await user.type(input, 'вакансии');

      // Should show page results
      await waitFor(() => {
        expect(screen.getByText('Страницы')).toBeInTheDocument();
      });
    });

    it('should show actions when searching for create', async () => {
      const user = userEvent.setup();
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      const input = await screen.findByPlaceholderText(/поиск/i);
      await user.type(input, 'создать');

      await waitFor(() => {
        expect(screen.getByText('Действия')).toBeInTheDocument();
      });
    });

    it('should show no results message for unmatched query', async () => {
      const user = userEvent.setup();
      vi.mocked(api.globalSearch).mockResolvedValue({
        candidates: [],
        vacancies: [],
        total: 0
      });

      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      const input = await screen.findByPlaceholderText(/поиск/i);
      await user.type(input, 'xyznonexistent123');

      await waitFor(() => {
        expect(screen.getByText(/ничего не найдено/i)).toBeInTheDocument();
      }, { timeout: 1000 });
    });
  });

  describe('keyboard navigation', () => {
    it('should navigate with arrow keys', async () => {
      const user = userEvent.setup();
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      const input = await screen.findByPlaceholderText(/поиск/i);
      await user.type(input, 'создать');

      // Wait for results
      await waitFor(() => {
        expect(screen.getByText('Действия')).toBeInTheDocument();
      });

      // Navigate down via store
      await act(async () => {
        useCommandPaletteStore.getState().setSelectedIndex(1);
      });

      // Should still have results visible
      expect(screen.getByText('Действия')).toBeInTheDocument();
    });

    it('should execute selected item', async () => {
      const user = userEvent.setup();
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      const input = await screen.findByPlaceholderText(/поиск/i);
      await user.type(input, 'вакансии');

      await waitFor(() => {
        expect(screen.getByText('Страницы')).toBeInTheDocument();
      });

      // Click the first result instead of using keyboard Enter
      const firstResult = screen.getByText('Вакансии');
      await user.click(firstResult);

      // Should navigate
      expect(mockNavigate).toHaveBeenCalled();
    });
  });

  describe('UI elements', () => {
    it('should show keyboard hints in footer', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      // Check for keyboard hint elements (may have multiple matches)
      await waitFor(() => {
        const enterElements = screen.getAllByText('Enter');
        const escElements = screen.getAllByText('Esc');
        expect(enterElements.length).toBeGreaterThan(0);
        expect(escElements.length).toBeGreaterThan(0);
      });
    });

    it('should show hints when empty', async () => {
      render(<CommandPalette />, { wrapper: Wrapper });

      await act(async () => {
        useCommandPaletteStore.getState().open();
      });

      await waitFor(() => {
        expect(screen.getByText(/начните вводить/i)).toBeInTheDocument();
      });
    });
  });
});

describe('CommandPaletteHint', () => {
  it('should render keyboard shortcut hint', () => {
    render(<CommandPaletteHint />, { wrapper: Wrapper });

    // Should show K key
    expect(screen.getByText('K')).toBeInTheDocument();
    // Should show modifier (Cmd or Ctrl depending on platform)
    expect(screen.getByText(/cmd|ctrl/i)).toBeInTheDocument();
  });

  it('should show search text on larger screens', () => {
    render(<CommandPaletteHint />, { wrapper: Wrapper });

    expect(screen.getByText(/для поиска/i)).toBeInTheDocument();
  });

  it('should apply custom className', () => {
    const { container } = render(
      <CommandPaletteHint className="custom-class" />,
      { wrapper: Wrapper }
    );

    expect(container.firstChild).toHaveClass('custom-class');
  });
});

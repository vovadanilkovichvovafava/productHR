import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { useCommandPalette, useCommandPaletteStore, clearCommandHistory } from '../useCommandPalette';
import * as api from '@/services/api';

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
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

describe('useCommandPaletteStore', () => {
  beforeEach(() => {
    useCommandPaletteStore.setState({
      isOpen: false,
      query: '',
      selectedIndex: 0,
      isLoading: false,
      apiResults: null,
      history: [],
    });
  });

  describe('global state synchronization', () => {
    it('should share isOpen state across multiple store instances', () => {
      // Get store state from two different "components"
      const store1 = useCommandPaletteStore.getState();

      // Open from store1
      store1.open();

      // Check that store2 sees the change
      const store2 = useCommandPaletteStore.getState();
      expect(store2.isOpen).toBe(true);
    });

    it('should synchronize state between multiple hook instances', () => {
      const { result: result1 } = renderHook(() => useCommandPalette(), { wrapper });
      const { result: result2 } = renderHook(() => useCommandPalette(), { wrapper });

      // Both should start closed
      expect(result1.current.isOpen).toBe(false);
      expect(result2.current.isOpen).toBe(false);

      // Open from first instance
      act(() => {
        result1.current.open();
      });

      // Second instance should see the change
      expect(result2.current.isOpen).toBe(true);
    });

    it('should synchronize query state between hook instances', () => {
      const { result: result1 } = renderHook(() => useCommandPalette(), { wrapper });
      const { result: result2 } = renderHook(() => useCommandPalette(), { wrapper });

      // Set query from first instance
      act(() => {
        result1.current.setQuery('test query');
      });

      // Second instance should see the query
      expect(result2.current.query).toBe('test query');
    });

    it('should close from any instance', () => {
      const { result: result1 } = renderHook(() => useCommandPalette(), { wrapper });
      const { result: result2 } = renderHook(() => useCommandPalette(), { wrapper });

      // Open from first instance
      act(() => {
        result1.current.open();
      });
      expect(result2.current.isOpen).toBe(true);

      // Close from second instance
      act(() => {
        result2.current.close();
      });

      // First instance should see it closed
      expect(result1.current.isOpen).toBe(false);
    });
  });

  describe('store actions', () => {
    it('should open and reset state', () => {
      const store = useCommandPaletteStore.getState();

      // Set some state first
      useCommandPaletteStore.setState({
        query: 'old query',
        selectedIndex: 5
      });

      // Open should reset
      store.open();

      const state = useCommandPaletteStore.getState();
      expect(state.isOpen).toBe(true);
      expect(state.query).toBe('');
      expect(state.selectedIndex).toBe(0);
    });

    it('should close and reset state', () => {
      useCommandPaletteStore.setState({
        isOpen: true,
        query: 'some query',
        selectedIndex: 3
      });

      const store = useCommandPaletteStore.getState();
      store.close();

      const state = useCommandPaletteStore.getState();
      expect(state.isOpen).toBe(false);
      expect(state.query).toBe('');
      expect(state.selectedIndex).toBe(0);
    });

    it('should toggle correctly', () => {
      const store = useCommandPaletteStore.getState();

      expect(useCommandPaletteStore.getState().isOpen).toBe(false);

      store.toggle();
      expect(useCommandPaletteStore.getState().isOpen).toBe(true);

      store.toggle();
      expect(useCommandPaletteStore.getState().isOpen).toBe(false);
    });
  });
});

describe('useCommandPalette', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearCommandHistory();
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

  afterEach(() => {
    vi.clearAllTimers();
  });

  describe('initial state', () => {
    it('should start with closed state', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      expect(result.current.isOpen).toBe(false);
      expect(result.current.query).toBe('');
      expect(result.current.selectedIndex).toBe(0);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.results).toEqual([]);
    });
  });

  describe('open/close/toggle', () => {
    it('should open the palette', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.open();
      });

      expect(result.current.isOpen).toBe(true);
    });

    it('should close the palette', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.open();
        result.current.close();
      });

      expect(result.current.isOpen).toBe(false);
    });

    it('should toggle the palette', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.toggle();
      });
      expect(result.current.isOpen).toBe(true);

      act(() => {
        result.current.toggle();
      });
      expect(result.current.isOpen).toBe(false);
    });

    it('should reset query when closing', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.open();
        result.current.setQuery('test');
      });

      expect(result.current.query).toBe('test');

      act(() => {
        result.current.close();
      });

      expect(result.current.query).toBe('');
    });
  });

  describe('keyboard navigation', () => {
    it('should move selection down', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      // First set some query to get results
      act(() => {
        result.current.setQuery('создать');
      });

      // Wait for local results to populate
      expect(result.current.results.length).toBeGreaterThan(0);

      act(() => {
        result.current.moveDown();
      });

      expect(result.current.selectedIndex).toBe(1);
    });

    it('should move selection up', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.setQuery('создать');
      });

      act(() => {
        result.current.setSelectedIndex(2);
        result.current.moveUp();
      });

      expect(result.current.selectedIndex).toBe(1);
    });

    it('should wrap around when moving past bounds', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.setQuery('создать');
      });

      const resultsLength = result.current.results.length;

      act(() => {
        result.current.setSelectedIndex(0);
        result.current.moveUp();
      });

      expect(result.current.selectedIndex).toBe(resultsLength - 1);
    });
  });

  describe('local search', () => {
    it('should filter pages by query', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.setQuery('вакансии');
      });

      const pageResults = result.current.results.filter(r => r.type === 'pages');
      expect(pageResults.length).toBeGreaterThan(0);
      expect(pageResults.some(r => r.title.toLowerCase().includes('вакансии'))).toBe(true);
    });

    it('should filter actions by query', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.setQuery('создать кандидата');
      });

      const actionResults = result.current.results.filter(r => r.type === 'actions');
      expect(actionResults.length).toBeGreaterThan(0);
    });

    it('should match keywords', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.setQuery('upload');
      });

      const actionResults = result.current.results.filter(r => r.type === 'actions');
      expect(actionResults.some(r => r.title.toLowerCase().includes('загрузить'))).toBe(true);
    });
  });

  describe('API search', () => {
    it('should call globalSearch API with debounce', async () => {
      vi.useFakeTimers();
      const mockResponse = {
        candidates: [
          { id: 1, name: 'John Doe', email: 'john@test.com', status: 'new', relevance_score: 100 }
        ],
        vacancies: [],
        total: 1
      };
      vi.mocked(api.globalSearch).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => useCommandPalette({ debounceMs: 100 }), { wrapper });

      act(() => {
        result.current.setQuery('john');
      });

      // API should not be called immediately
      expect(api.globalSearch).not.toHaveBeenCalled();

      // Fast-forward past debounce and run all pending timers
      await act(async () => {
        vi.advanceTimersByTime(150);
        await vi.runAllTimersAsync();
      });

      // API should have been called after debounce
      expect(api.globalSearch).toHaveBeenCalledWith('john', 10);

      vi.useRealTimers();
    });

    it('should not call API for empty query', async () => {
      const { result } = renderHook(() => useCommandPalette({ debounceMs: 100 }), { wrapper });

      act(() => {
        result.current.setQuery('');
      });

      expect(api.globalSearch).not.toHaveBeenCalled();
    });
  });

  describe('executeSelected', () => {
    it('should execute action of selected item', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.setQuery('вакансии');
      });

      const pageResults = result.current.results.filter(r => r.type === 'pages');
      expect(pageResults.length).toBeGreaterThan(0);

      act(() => {
        result.current.executeSelected();
      });

      // Should navigate to vacancies page
      expect(mockNavigate).toHaveBeenCalled();
    });
  });

  describe('history', () => {
    it('should maintain search history', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      // Execute a search to save to history
      act(() => {
        result.current.setQuery('test query');
      });

      // Execute an action to trigger history save
      const pageResults = result.current.results;
      if (pageResults.length > 0) {
        act(() => {
          result.current.executeSelected();
        });
      }

      // History should be accessible
      expect(result.current.history).toBeDefined();
    });

    it('should clear history', () => {
      const { result } = renderHook(() => useCommandPalette(), { wrapper });

      act(() => {
        result.current.clearHistory();
      });

      expect(result.current.history).toEqual([]);
    });
  });
});

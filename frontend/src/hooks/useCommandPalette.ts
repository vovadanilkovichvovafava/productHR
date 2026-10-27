import { useCallback, useRef, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { create } from 'zustand';
import { globalSearch, type GlobalSearchResponse } from '@/services/api';
import { getLocalStorage, setLocalStorage, removeLocalStorage } from '@/utils/localStorage';

/**
 * Local storage keys
 */
const COMMAND_HISTORY_KEY = 'hr_command_palette_history';
const MAX_HISTORY_ITEMS = 10;

/**
 * Result category type
 */
export type ResultCategory = 'candidates' | 'vacancies' | 'actions' | 'pages';

/**
 * Search result item
 */
export interface CommandPaletteItem {
  id: string;
  type: ResultCategory;
  title: string;
  subtitle?: string;
  icon: string;
  action: () => void;
  keywords?: string[];
  shortcut?: string;
}

/**
 * Action item definition
 */
export interface ActionItem {
  id: string;
  title: string;
  subtitle?: string;
  icon: string;
  shortcut?: string;
  keywords: string[];
  action: () => void;
}

/**
 * Page item definition
 */
export interface PageItem {
  id: string;
  title: string;
  path: string;
  icon: string;
  keywords: string[];
}

/**
 * Get command history from localStorage
 */
function getCommandHistory(): string[] {
  return getLocalStorage<string[]>(COMMAND_HISTORY_KEY, []);
}

/**
 * Save command to history
 */
function saveToHistory(command: string): void {
  const history = getCommandHistory();
  const filtered = history.filter(q => q.toLowerCase() !== command.toLowerCase());
  filtered.unshift(command);
  const limited = filtered.slice(0, MAX_HISTORY_ITEMS);
  setLocalStorage(COMMAND_HISTORY_KEY, limited);
}

/**
 * Clear command history
 */
export function clearCommandHistory(): void {
  removeLocalStorage(COMMAND_HISTORY_KEY);
}

/**
 * Static pages available in the app
 */
const PAGES: PageItem[] = [
  { id: 'page-candidates', title: 'Все кандидаты', path: '/all-candidates', icon: 'UserCheck', keywords: ['кандидаты', 'база', 'соискатели', 'candidates'] },
  { id: 'page-vacancies', title: 'Вакансии', path: '/vacancies', icon: 'Briefcase', keywords: ['вакансии', 'должности', 'vacancies', 'jobs'] },
  { id: 'page-dashboard', title: 'Главная', path: '/dashboard', icon: 'LayoutDashboard', keywords: ['главная', 'дашборд', 'dashboard', 'home'] },
  { id: 'page-chats', title: 'Чаты', path: '/chats', icon: 'MessageSquare', keywords: ['чаты', 'сообщения', 'переписка', 'chats'] },
  { id: 'page-contacts', title: 'Контакты', path: '/all-candidates', icon: 'Users', keywords: ['контакты', 'люди', 'contacts'] },
  { id: 'page-calls', title: 'Созвоны', path: '/calls', icon: 'Phone', keywords: ['созвоны', 'звонки', 'calls', 'записи'] },
  { id: 'page-settings', title: 'Настройки', path: '/settings', icon: 'Settings', keywords: ['настройки', 'параметры', 'settings'] },
  { id: 'page-trash', title: 'Корзина', path: '/trash', icon: 'Trash2', keywords: ['корзина', 'удаленные', 'trash'] },
];

/**
 * Zustand store for Command Palette global state
 * This ensures all components share the same isOpen state
 */
interface CommandPaletteStore {
  isOpen: boolean;
  query: string;
  selectedIndex: number;
  isLoading: boolean;
  apiResults: GlobalSearchResponse | null;
  history: string[];

  // Actions
  open: () => void;
  close: () => void;
  toggle: () => void;
  setQuery: (query: string) => void;
  setSelectedIndex: (index: number) => void;
  setIsLoading: (loading: boolean) => void;
  setApiResults: (results: GlobalSearchResponse | null) => void;
  setHistory: (history: string[]) => void;
}

export const useCommandPaletteStore = create<CommandPaletteStore>((set, get) => ({
  isOpen: false,
  query: '',
  selectedIndex: 0,
  isLoading: false,
  apiResults: null,
  history: getCommandHistory(),

  open: () => set({ isOpen: true, query: '', selectedIndex: 0, apiResults: null }),
  close: () => set({ isOpen: false, query: '', selectedIndex: 0 }),
  toggle: () => {
    const { isOpen, open, close } = get();
    if (isOpen) {
      close();
    } else {
      open();
    }
  },
  setQuery: (query) => set({ query, selectedIndex: 0 }),
  setSelectedIndex: (selectedIndex) => set({ selectedIndex }),
  setIsLoading: (isLoading) => set({ isLoading }),
  setApiResults: (apiResults) => set({ apiResults }),
  setHistory: (history) => set({ history }),
}));

/**
 * Return type for the useCommandPalette hook
 */
export interface UseCommandPaletteReturn {
  /** Whether the palette is open */
  isOpen: boolean;
  /** Open the palette */
  open: () => void;
  /** Close the palette */
  close: () => void;
  /** Toggle the palette */
  toggle: () => void;
  /** Current search query */
  query: string;
  /** Set search query */
  setQuery: (query: string) => void;
  /** Search results grouped by category */
  results: CommandPaletteItem[];
  /** Whether search is loading */
  isLoading: boolean;
  /** Selected index for keyboard navigation */
  selectedIndex: number;
  /** Set selected index */
  setSelectedIndex: (index: number) => void;
  /** Move selection up */
  moveUp: () => void;
  /** Move selection down */
  moveDown: () => void;
  /** Execute selected item */
  executeSelected: () => void;
  /** Command history */
  history: string[];
  /** Clear history */
  clearHistory: () => void;
  /** Recent searches */
  recentSearches: string[];
}

/**
 * Hook for managing the Command Palette (Cmd+K global search).
 *
 * Features:
 * - Global keyboard shortcut (Cmd+K / Ctrl+K)
 * - Search across candidates, vacancies, actions, and pages
 * - Keyboard navigation (arrows, Enter, Escape)
 * - Debounced API calls
 * - Search history
 *
 * @param options.debounceMs Debounce time for API calls (default: 300)
 * @param options.enableKeyboardShortcuts Enable global keyboard shortcuts (default: true)
 *
 * @example
 * ```tsx
 * const { isOpen, open, query, setQuery, results } = useCommandPalette();
 *
 * return (
 *   <CommandPalette
 *     isOpen={isOpen}
 *     query={query}
 *     onQueryChange={setQuery}
 *     results={results}
 *   />
 * );
 * ```
 */
export function useCommandPalette(options: {
  debounceMs?: number;
  enableKeyboardShortcuts?: boolean;
} = {}): UseCommandPaletteReturn {
  const { debounceMs = 300, enableKeyboardShortcuts = true } = options;

  // Use global store for shared state
  const {
    isOpen,
    query,
    selectedIndex,
    isLoading,
    apiResults,
    history,
    open,
    close,
    toggle,
    setQuery: storeSetQuery,
    setSelectedIndex,
    setIsLoading,
    setApiResults,
    setHistory,
  } = useCommandPaletteStore();

  const navigate = useNavigate();
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Define actions
  const actions: ActionItem[] = useMemo(() => [
    {
      id: 'action-create-candidate',
      title: 'Создать кандидата',
      subtitle: 'Добавить нового кандидата в базу',
      icon: 'UserPlus',
      keywords: ['создать', 'добавить', 'кандидат', 'новый', 'create', 'add', 'candidate'],
      action: () => {
        navigate('/all-candidates');
        close();
      }
    },
    {
      id: 'action-create-vacancy',
      title: 'Создать вакансию',
      subtitle: 'Открыть новую вакансию',
      icon: 'FilePlus',
      keywords: ['создать', 'добавить', 'вакансия', 'новая', 'create', 'add', 'vacancy'],
      action: () => {
        navigate('/vacancies?action=create');
        close();
      }
    },
    {
      id: 'action-upload-resume',
      title: 'Загрузить резюме',
      subtitle: 'Импорт резюме из файла',
      icon: 'Upload',
      keywords: ['загрузить', 'импорт', 'резюме', 'файл', 'upload', 'import', 'resume', 'cv'],
      action: () => {
        navigate('/all-candidates');
        close();
      }
    },
    {
      id: 'action-start-call',
      title: 'Записать звонок',
      subtitle: 'Начать запись созвона',
      icon: 'Video',
      keywords: ['записать', 'звонок', 'созвон', 'видео', 'record', 'call', 'meeting'],
      action: () => {
        navigate('/calls?action=record');
        close();
      }
    }
  ], [navigate, close]);

  // Filter local items (pages and actions)
  const filterLocalItems = useCallback((searchQuery: string): CommandPaletteItem[] => {
    if (!searchQuery.trim()) return [];

    const lowerQuery = searchQuery.toLowerCase();
    const results: CommandPaletteItem[] = [];

    // Filter pages
    PAGES.forEach(page => {
      const matchesTitle = page.title.toLowerCase().includes(lowerQuery);
      const matchesKeywords = page.keywords.some(kw => kw.toLowerCase().includes(lowerQuery));

      if (matchesTitle || matchesKeywords) {
        results.push({
          id: page.id,
          type: 'pages',
          title: page.title,
          icon: page.icon,
          action: () => {
            navigate(page.path);
            close();
            saveToHistory(searchQuery);
          }
        });
      }
    });

    // Filter actions
    actions.forEach(action => {
      const matchesTitle = action.title.toLowerCase().includes(lowerQuery);
      const matchesKeywords = action.keywords.some(kw => kw.toLowerCase().includes(lowerQuery));

      if (matchesTitle || matchesKeywords) {
        results.push({
          id: action.id,
          type: 'actions',
          title: action.title,
          subtitle: action.subtitle,
          icon: action.icon,
          shortcut: action.shortcut,
          action: () => {
            action.action();
            saveToHistory(searchQuery);
          }
        });
      }
    });

    return results;
  }, [actions, navigate, close]);

  // Convert API results to CommandPaletteItems
  const convertApiResults = useCallback((response: GlobalSearchResponse, searchQuery: string): CommandPaletteItem[] => {
    const items: CommandPaletteItem[] = [];

    // Candidates
    response.candidates?.forEach(candidate => {
      items.push({
        id: `candidate-${candidate.id}`,
        type: 'candidates',
        title: candidate.name,
        subtitle: [candidate.position, candidate.email, candidate.phone].filter(Boolean).join(' | '),
        icon: 'UserCheck',
        action: () => {
          navigate(`/all-candidates?entity=${candidate.id}`);
          close();
          saveToHistory(searchQuery);
        }
      });
    });

    // Vacancies
    response.vacancies?.forEach(vacancy => {
      items.push({
        id: `vacancy-${vacancy.id}`,
        type: 'vacancies',
        title: vacancy.title,
        subtitle: vacancy.department_name || vacancy.location,
        icon: 'Briefcase',
        action: () => {
          navigate(`/vacancies/${vacancy.id}`);
          close();
          saveToHistory(searchQuery);
        }
      });
    });

    return items;
  }, [navigate, close]);

  // Combined results
  const results = useMemo((): CommandPaletteItem[] => {
    const localItems = filterLocalItems(query);

    if (!apiResults) return localItems;

    const apiItems = convertApiResults(apiResults, query);

    // Sort: actions first, then pages, then candidates, then vacancies
    const sortOrder: Record<ResultCategory, number> = {
      actions: 0,
      pages: 1,
      candidates: 2,
      vacancies: 3
    };

    return [...apiItems, ...localItems].sort((a, b) => sortOrder[a.type] - sortOrder[b.type]);
  }, [query, apiResults, filterLocalItems, convertApiResults]);

  // Perform search
  const performSearch = useCallback(async (searchQuery: string) => {
    // Clear previous debounce
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Abort previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    if (!searchQuery.trim()) {
      setApiResults(null);
      setIsLoading(false);
      return;
    }

    // Debounce API call
    debounceTimerRef.current = setTimeout(async () => {
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setIsLoading(true);

      try {
        const response = await globalSearch(searchQuery, 10);
        if (!controller.signal.aborted) {
          setApiResults(response);
        }
      } catch (err) {
        if (!(err instanceof Error && err.name === 'AbortError')) {
          console.error('Global search failed:', err);
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }, debounceMs);
  }, [debounceMs, setApiResults, setIsLoading]);

  // Handle query change
  const handleSetQuery = useCallback((newQuery: string) => {
    storeSetQuery(newQuery);
    performSearch(newQuery);
  }, [storeSetQuery, performSearch]);

  // Keyboard navigation
  const moveUp = useCallback(() => {
    setSelectedIndex(selectedIndex > 0 ? selectedIndex - 1 : results.length - 1);
  }, [selectedIndex, results.length, setSelectedIndex]);

  const moveDown = useCallback(() => {
    setSelectedIndex(selectedIndex < results.length - 1 ? selectedIndex + 1 : 0);
  }, [selectedIndex, results.length, setSelectedIndex]);

  const executeSelected = useCallback(() => {
    if (results[selectedIndex]) {
      results[selectedIndex].action();
    }
  }, [results, selectedIndex]);

  // Clear history
  const clearHistoryHandler = useCallback(() => {
    clearCommandHistory();
    setHistory([]);
  }, [setHistory]);

  // Global keyboard shortcut - only one instance should register this
  useEffect(() => {
    if (!enableKeyboardShortcuts) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K
      const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
      const modifier = isMac ? e.metaKey : e.ctrlKey;

      if (modifier && e.key === 'k') {
        e.preventDefault();
        toggle();
        return;
      }

      // Handle keyboard navigation when open
      if (isOpen) {
        switch (e.key) {
          case 'Escape':
            e.preventDefault();
            close();
            break;
          case 'ArrowUp':
            e.preventDefault();
            moveUp();
            break;
          case 'ArrowDown':
            e.preventDefault();
            moveDown();
            break;
          case 'Enter':
            e.preventDefault();
            executeSelected();
            break;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [enableKeyboardShortcuts, isOpen, toggle, close, moveUp, moveDown, executeSelected]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [results.length, setSelectedIndex]);

  return {
    isOpen,
    open,
    close,
    toggle,
    query,
    setQuery: handleSetQuery,
    results,
    isLoading,
    selectedIndex,
    setSelectedIndex,
    moveUp,
    moveDown,
    executeSelected,
    history,
    clearHistory: clearHistoryHandler,
    recentSearches: history
  };
}

export default useCommandPalette;

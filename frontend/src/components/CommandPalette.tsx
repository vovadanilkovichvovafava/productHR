import { useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  X,
  Loader2,
  UserCheck,
  Briefcase,
  Settings,
  LayoutDashboard,
  MessageSquare,
  Users,
  Phone,
  Trash2,
  UserPlus,
  FilePlus,
  Upload,
  Video,
  Command,
  ArrowRight,
  Clock,
  type LucideIcon
} from 'lucide-react';
import clsx from 'clsx';
import { useCommandPalette, type CommandPaletteItem, type ResultCategory } from '@/hooks/useCommandPalette';
import { backdropClose } from '@/utils/backdropClose';

/**
 * Icon mapping for dynamic icons
 */
const iconMap: Record<string, LucideIcon> = {
  UserCheck,
  Briefcase,
  Settings,
  LayoutDashboard,
  MessageSquare,
  Users,
  Phone,
  Trash2,
  UserPlus,
  FilePlus,
  Upload,
  Video
};

/**
 * Category labels in Russian
 */
const categoryLabels: Record<ResultCategory, string> = {
  candidates: 'Кандидаты',
  vacancies: 'Вакансии',
  actions: 'Действия',
  pages: 'Страницы'
};

/**
 * Category icons
 */
const categoryIcons: Record<ResultCategory, LucideIcon> = {
  candidates: UserCheck,
  vacancies: Briefcase,
  actions: Command,
  pages: LayoutDashboard
};

/**
 * Highlight matching text in search results
 */
function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;

  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const index = lowerText.indexOf(lowerQuery);

  if (index === -1) return text;

  return (
    <>
      {text.slice(0, index)}
      <span className="bg-accent-500/30 text-accent-300 px-0.5 rounded">
        {text.slice(index, index + query.length)}
      </span>
      {text.slice(index + query.length)}
    </>
  );
}

/**
 * Group results by category
 */
function groupResultsByCategory(results: CommandPaletteItem[]): Record<ResultCategory, CommandPaletteItem[]> {
  return results.reduce((acc, item) => {
    if (!acc[item.type]) {
      acc[item.type] = [];
    }
    acc[item.type].push(item);
    return acc;
  }, {} as Record<ResultCategory, CommandPaletteItem[]>);
}

/**
 * Get flat index for keyboard navigation
 */
function getFlatIndex(groupedResults: Record<ResultCategory, CommandPaletteItem[]>, category: ResultCategory, indexInCategory: number): number {
  const categories: ResultCategory[] = ['actions', 'pages', 'candidates', 'vacancies'];
  let flatIndex = 0;

  for (const cat of categories) {
    if (cat === category) {
      return flatIndex + indexInCategory;
    }
    flatIndex += groupedResults[cat]?.length || 0;
  }

  return flatIndex + indexInCategory;
}

/**
 * Command Palette Component
 *
 * A global search interface similar to VS Code, Linear, or Notion.
 * Opens with Cmd+K (Mac) or Ctrl+K (Windows/Linux).
 *
 * Features:
 * - Search across candidates, vacancies, actions, and pages
 * - Keyboard navigation (arrows, Enter, Escape)
 * - Result highlighting
 * - Category grouping
 * - Recent searches
 *
 * @example
 * ```tsx
 * // In Layout.tsx
 * <CommandPalette />
 * ```
 */
export default function CommandPalette() {
  const {
    isOpen,
    close,
    query,
    setQuery,
    results,
    isLoading,
    selectedIndex,
    setSelectedIndex,
    recentSearches
  } = useCommandPalette();

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      // Small delay to ensure modal is rendered
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current && results.length > 0) {
      const selectedElement = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      selectedElement?.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex, results.length]);

  // Handle click outside to close
  // Group results by category
  const groupedResults = groupResultsByCategory(results);
  const categoryOrder: ResultCategory[] = ['actions', 'pages', 'candidates', 'vacancies'];
  const hasResults = results.length > 0;
  const showRecentSearches = !query && recentSearches.length > 0;

  // Platform-specific shortcut key
  const isMac = typeof navigator !== 'undefined' && navigator.platform.toUpperCase().indexOf('MAC') >= 0;
  const modifierKey = isMac ? 'Cmd' : 'Ctrl';

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm"
          {...backdropClose(close)}
          role="dialog"
          aria-modal="true"
          aria-label="Command palette search"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="w-full max-w-2xl mx-4"
          >
            <div className="bg-dark-800 border border-white/10 rounded-2xl shadow-2xl shadow-black/50 overflow-hidden">
              {/* Search Input */}
              <div className="flex items-center gap-3 px-4 py-3 border-b border-white/10">
                <div className="flex-shrink-0">
                  {isLoading ? (
                    <Loader2 className="w-5 h-5 text-accent-400 animate-spin" aria-hidden="true" />
                  ) : (
                    <Search className="w-5 h-5 text-white/40" aria-hidden="true" />
                  )}
                </div>

                <input
                  ref={inputRef}
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Поиск кандидатов, вакансий, страниц..."
                  className="flex-1 bg-transparent text-white placeholder:text-white/40 focus:outline-none text-base"
                  autoComplete="off"
                  spellCheck={false}
                  role="combobox"
                  aria-expanded={hasResults}
                  aria-controls="command-palette-results"
                  aria-activedescendant={hasResults && selectedIndex >= 0 ? `command-palette-item-${selectedIndex}` : undefined}
                  aria-label="Поиск кандидатов, вакансий, страниц"
                />

                <div className="flex items-center gap-2 flex-shrink-0">
                  <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs text-white/40 glass-light rounded-lg" aria-hidden="true">
                    Esc
                  </kbd>
                  <button
                    onClick={close}
                    className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                    aria-label="Закрыть поиск"
                  >
                    <X className="w-4 h-4 text-white/60" aria-hidden="true" />
                  </button>
                </div>
              </div>

              {/* Results */}
              <div
                ref={listRef}
                className="max-h-[400px] overflow-y-auto"
                id="command-palette-results"
                role="listbox"
                aria-label="Результаты поиска"
              >
                {/* Recent Searches */}
                {showRecentSearches && (
                  <div className="p-2">
                    <div className="px-3 py-2 flex items-center gap-2 text-xs text-white/40 uppercase tracking-wide" id="recent-searches-label">
                      <Clock className="w-3.5 h-3.5" aria-hidden="true" />
                      Недавние поиски
                    </div>
                    <div role="group" aria-labelledby="recent-searches-label">
                      {recentSearches.slice(0, 5).map((search) => (
                        <button
                          key={search}
                          onClick={() => setQuery(search)}
                          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left hover:bg-dark-800/50 transition-colors"
                          role="option"
                          aria-label={`Искать: ${search}`}
                        >
                          <Clock className="w-4 h-4 text-white/30 flex-shrink-0" aria-hidden="true" />
                          <span className="text-sm text-white/70 truncate">{search}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* No Results */}
                {query && !hasResults && !isLoading && (
                  <div className="px-4 py-8 text-center" role="status" aria-live="polite">
                    <Search className="w-12 h-12 text-white/20 mx-auto mb-3" aria-hidden="true" />
                    <p className="text-white/60 text-sm">
                      Ничего не найдено по запросу "<span className="text-white/80">{query}</span>"
                    </p>
                    <p className="text-white/40 text-xs mt-1">
                      Попробуйте изменить запрос или проверить написание
                    </p>
                  </div>
                )}

                {/* Grouped Results */}
                {hasResults && categoryOrder.map((category) => {
                  const items = groupedResults[category];
                  if (!items?.length) return null;

                  const CategoryIcon = categoryIcons[category];

                  return (
                    <div key={category} className="p-2">
                      <div className="px-3 py-2 flex items-center gap-2 text-xs text-white/40 uppercase tracking-wide" id={`category-${category}-label`}>
                        <CategoryIcon className="w-3.5 h-3.5" aria-hidden="true" />
                        {categoryLabels[category]}
                        <span className="ml-auto text-white/30">{items.length}</span>
                      </div>

                      {items.map((item, indexInCategory) => {
                        const flatIndex = getFlatIndex(groupedResults, category, indexInCategory);
                        const isSelected = flatIndex === selectedIndex;
                        const ItemIcon = iconMap[item.icon] || Users;

                        return (
                          <button
                            key={item.id}
                            id={`command-palette-item-${flatIndex}`}
                            data-index={flatIndex}
                            onClick={() => item.action()}
                            onMouseEnter={() => setSelectedIndex(flatIndex)}
                            className={clsx(
                              'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors group',
                              isSelected ? 'bg-accent-500/20 text-white' : 'hover:bg-dark-800/50 text-white/80'
                            )}
                            role="option"
                            aria-selected={isSelected}
                          >
                            <div className={clsx(
                              'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0',
                              isSelected ? 'bg-accent-500/30' : 'glass-light'
                            )}>
                              <ItemIcon className={clsx(
                                'w-4 h-4',
                                isSelected ? 'text-accent-400' : 'text-white/60'
                              )} aria-hidden="true" />
                            </div>

                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium truncate">
                                {highlightMatch(item.title, query)}
                              </div>
                              {item.subtitle && (
                                <div className="text-xs text-white/50 truncate mt-0.5">
                                  {highlightMatch(item.subtitle, query)}
                                </div>
                              )}
                            </div>

                            {item.shortcut && (
                              <kbd className="hidden sm:inline-flex items-center px-2 py-1 text-xs text-white/40 glass-light rounded" aria-hidden="true">
                                {item.shortcut}
                              </kbd>
                            )}

                            <ArrowRight className={clsx(
                              'w-4 h-4 flex-shrink-0 transition-opacity',
                              isSelected ? 'opacity-100 text-accent-400' : 'opacity-0'
                            )} aria-hidden="true" />
                          </button>
                        );
                      })}
                    </div>
                  );
                })}

                {/* Hints */}
                {!query && !showRecentSearches && (
                  <div className="px-4 py-6 text-center">
                    <Command className="w-10 h-10 text-white/20 mx-auto mb-3" aria-hidden="true" />
                    <p className="text-white/50 text-sm mb-4">
                      Начните вводить для поиска
                    </p>
                    <div className="flex flex-wrap justify-center gap-2 text-xs">
                      <span className="px-2 py-1 glass-light rounded-lg text-white/40">
                        Кандидаты
                      </span>
                      <span className="px-2 py-1 glass-light rounded-lg text-white/40">
                        Вакансии
                      </span>
                      <span className="px-2 py-1 glass-light rounded-lg text-white/40">
                        Страницы
                      </span>
                      <span className="px-2 py-1 glass-light rounded-lg text-white/40">
                        Действия
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Footer with keyboard hints */}
              <div className="px-4 py-2.5 border-t border-white/5 flex items-center justify-between text-xs text-white/30">
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 glass-light rounded text-white/50">Enter</kbd>
                    <span className="hidden sm:inline">выбрать</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1 py-0.5 glass-light rounded text-white/50">...</kbd>
                    <span className="hidden sm:inline">навигация</span>
                  </span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 glass-light rounded text-white/50">Esc</kbd>
                    <span className="hidden sm:inline">закрыть</span>
                  </span>
                </div>

                <div className="hidden sm:flex items-center gap-1.5">
                  <kbd className="px-1.5 py-0.5 glass-light rounded text-white/50">{modifierKey}</kbd>
                  <span>+</span>
                  <kbd className="px-1.5 py-0.5 glass-light rounded text-white/50">K</kbd>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * Keyboard hint component for showing in the UI
 */
export function CommandPaletteHint({ className }: { className?: string }) {
  const isMac = typeof navigator !== 'undefined' && navigator.platform.toUpperCase().indexOf('MAC') >= 0;

  return (
    <div className={clsx(
      'flex items-center gap-1.5 text-xs text-white/40 cursor-pointer hover:text-white/60 transition-colors',
      className
    )}>
      <kbd className="px-1.5 py-0.5 glass-light rounded">
        {isMac ? 'Cmd' : 'Ctrl'}
      </kbd>
      <span>+</span>
      <kbd className="px-1.5 py-0.5 glass-light rounded">K</kbd>
      <span className="ml-1 hidden sm:inline">для поиска</span>
    </div>
  );
}

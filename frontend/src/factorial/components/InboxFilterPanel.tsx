import { useEffect, useRef, useState } from 'react';
import { Filter, Search, ChevronRight } from 'lucide-react';
import { cn } from '@/factorial/lib/cn';
import FilterDateRange from './FilterDateRange';
import {
  DEPARTMENTS,
  ROLES,
  EMPLOYEE_STATUSES,
  LEGAL_ENTITIES,
  LOCATIONS,
  EMPLOYEE_NAMES,
} from '@/factorial/mocks/inboxFilters';

interface Category {
  label: string;
  options: string[];
  /** date-range picker instead of an option list */
  date?: boolean;
  /** rows render with a leading expand chevron (›), like Factorial's Роль */
  expandable?: boolean;
}

const CATEGORIES: Category[] = [
  { label: 'Вовлечённый', options: [] },
  { label: 'Категория', options: [] },
  { label: 'Дата создания', options: [], date: true },
  { label: 'Место работы', options: LOCATIONS },
  { label: 'Команда', options: DEPARTMENTS },
  { label: 'Юридическое лицо', options: LEGAL_ENTITIES },
  { label: 'Подчиняется', options: EMPLOYEE_NAMES },
  { label: 'Менеджер по утверждению', options: EMPLOYEE_NAMES },
  { label: 'Роль', options: ROLES, expandable: true },
  { label: 'Статус сотрудника', options: EMPLOYEE_STATUSES },
];

/**
 * Inbox filter popover — 1-to-1 with Factorial, real account data.
 * Left: 10 categories. Right: per-category content (date-range / checkbox list /
 * role list with expand chevrons / empty). Footer: Очистить / Применить.
 */
export default function InboxFilterPanel() {
  const [open, setOpen] = useState(false);
  const [activeCat, setActiveCat] = useState(0);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<Record<number, string[]>>({});
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const cat = CATEGORIES[activeCat];
  const sel = selected[activeCat] ?? [];
  const filteredOptions = cat.options.filter((o) => o.toLowerCase().includes(query.toLowerCase()));

  const toggleOption = (opt: string) => {
    setSelected((prev) => {
      const cur = prev[activeCat] ?? [];
      const next = cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt];
      return { ...prev, [activeCat]: next };
    });
  };

  const clearAll = () => {
    setSelected({});
    setQuery('');
    setFrom('');
    setTo('');
    setActiveCat(0);
  };

  // Count badge per category (date counts as 1 if either bound set)
  const catCount = (i: number) => {
    if (CATEGORIES[i].date) return from || to ? 1 : 0;
    return (selected[i] ?? []).length;
  };

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'w-9 h-9 rounded-fx-lg border bg-white flex items-center justify-center hover:bg-sidebar-hover transition-colors',
          open ? 'border-primary text-primary' : 'border-card-border-soft text-text-muted',
        )}
        title="Фильтр"
        aria-label="Фильтр"
      >
        <Filter className="w-4 h-4" />
      </button>

      {open && (
        <div className="absolute left-0 mt-2 z-30 w-[600px] bg-white rounded-card shadow-card-hover border border-card-border-soft overflow-hidden">
          <div className="grid grid-cols-[210px_1fr]">
            {/* Left — category list */}
            <div className="border-r border-card-border-soft py-2 max-h-[360px] overflow-y-auto scrollbar-thin">
              {CATEGORIES.map((c, i) => {
                const count = catCount(i);
                return (
                  <button
                    key={c.label}
                    type="button"
                    onClick={() => {
                      setActiveCat(i);
                      setQuery('');
                    }}
                    className={cn(
                      'w-full flex items-center justify-between gap-2 text-left px-4 py-2 text-fx-sm transition-colors',
                      i === activeCat
                        ? 'bg-sidebar-active text-text-primary font-medium'
                        : 'text-text-secondary hover:bg-sidebar-hover',
                    )}
                  >
                    <span className="truncate">{c.label}</span>
                    {count > 0 && (
                      <span className="shrink-0 text-fx-xs bg-primary text-white rounded-full px-1.5 py-0.5 leading-none">
                        {count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Right — per-category content */}
            <div className="p-3 flex flex-col min-h-[330px]">
              {cat.date ? (
                <FilterDateRange
                  from={from}
                  to={to}
                  onChange={(f, t) => {
                    setFrom(f);
                    setTo(t);
                  }}
                />
              ) : (
                <>
                  <div className="relative mb-3">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Опции поиска..."
                      className="w-full pl-9 pr-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm focus:outline-none focus:border-border-hover"
                    />
                  </div>
                  <div className="flex items-center justify-between py-1.5 px-1 text-fx-sm border-b border-card-border-soft">
                    <span className="text-text-secondary">{sel.length} выбрано</span>
                    <input
                      type="checkbox"
                      className="rounded border-card-border-soft accent-primary"
                      checked={filteredOptions.length > 0 && filteredOptions.every((o) => sel.includes(o))}
                      onChange={(e) =>
                        setSelected((prev) => ({
                          ...prev,
                          [activeCat]: e.target.checked ? [...filteredOptions] : [],
                        }))
                      }
                    />
                  </div>
                  {filteredOptions.length === 0 ? (
                    <div className="flex-1 flex items-center justify-center text-fx-sm text-text-muted">
                      Результаты не найдены
                    </div>
                  ) : (
                    <div className="flex-1 overflow-y-auto scrollbar-thin py-1 max-h-[230px]">
                      {filteredOptions.map((opt) => (
                        <label
                          key={opt}
                          className="flex items-center gap-2 px-1 py-2 text-fx-sm cursor-pointer hover:bg-sidebar-hover rounded"
                        >
                          {cat.expandable && (
                            <ChevronRight className="w-4 h-4 text-text-muted shrink-0" />
                          )}
                          <span className="flex-1 truncate">{opt}</span>
                          <input
                            type="checkbox"
                            className="rounded border-card-border-soft accent-primary shrink-0"
                            checked={sel.includes(opt)}
                            onChange={() => toggleOption(opt)}
                          />
                        </label>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between gap-2 px-3 py-3 border-t border-card-border-soft">
            <button
              type="button"
              onClick={clearAll}
              className="px-4 py-2 text-fx-sm font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
            >
              Очистить фильтры
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-4 py-2 text-fx-sm font-medium rounded-fx-lg bg-primary hover:bg-primary-hover text-white"
            >
              Применить фильтры
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

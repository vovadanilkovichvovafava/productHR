import { ReactNode } from 'react';
import { Search, Filter, Download } from 'lucide-react';
import { cn } from '@/factorial/lib/cn';

interface ToolbarProps {
  searchValue?: string;
  onSearchChange?: (v: string) => void;
  searchPlaceholder?: string;
  filterAction?: () => void;
  moreActions?: ReactNode;
  exportAction?: () => void;
  primaryCta?: { label: string; onClick: () => void };
  className?: string;
}

export default function Toolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Поиск...',
  filterAction,
  moreActions,
  exportAction,
  primaryCta,
  className,
}: ToolbarProps) {
  return (
    <div className={cn('flex items-center justify-between gap-3 mb-4', className)}>
      <div className="flex items-center gap-2 flex-1 max-w-md">
        {onSearchChange && (
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
            <input
              type="text"
              value={searchValue ?? ''}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full pl-9 pr-3 py-2 rounded-fx-lg border border-border bg-white text-fx-sm focus:border-border-hover focus:outline-none"
            />
          </div>
        )}
        {filterAction && (
          <button
            type="button"
            onClick={filterAction}
            className="p-2 rounded-fx-lg border border-border bg-white hover:bg-sidebar-hover"
            title="Фильтр"
          >
            <Filter className="w-4 h-4 text-text-muted" />
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        {moreActions}
        {exportAction && (
          <button
            type="button"
            onClick={exportAction}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-fx-lg border border-border bg-white hover:bg-sidebar-hover text-fx-sm"
          >
            <Download className="w-4 h-4 text-text-muted" /> Экспорт данных
          </button>
        )}
        {primaryCta && (
          <button
            type="button"
            onClick={primaryCta.onClick}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-fx-lg bg-primary hover:bg-primary-hover text-white text-fx-base font-medium"
          >
            <span className="text-fx-base leading-none">+</span> {primaryCta.label}
          </button>
        )}
      </div>
    </div>
  );
}

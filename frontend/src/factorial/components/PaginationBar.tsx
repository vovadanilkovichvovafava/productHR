import { ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/factorial/lib/cn';

interface PaginationBarProps {
  current: number;
  total: number;
  pageSize: number;
  onChange: (page: number) => void;
}

export default function PaginationBar({ current, total, pageSize, onChange }: PaginationBarProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = (current - 1) * pageSize + 1;
  const to = Math.min(current * pageSize, total);

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-border text-fx-sm">
      <span className="text-text-muted">{from}–{to} из {total} элементов</span>
      <nav aria-label="Навигация по пагинации" className="flex items-center gap-1">
        <button
          type="button"
          disabled={current === 1}
          onClick={() => onChange(current - 1)}
          className="p-1.5 rounded hover:bg-sidebar-hover disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Предыдущая"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        {Array.from({ length: pages }, (_, i) => i + 1).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onChange(p)}
            className={cn(
              'min-w-[28px] px-2 py-1 rounded text-fx-xs font-medium',
              p === current ? 'bg-sidebar-active text-text-primary' : 'hover:bg-sidebar-hover text-text-secondary'
            )}
            aria-label={`Перейти на страницу ${p}`}
          >
            {p}
          </button>
        ))}
        <button
          type="button"
          disabled={current === pages}
          onClick={() => onChange(current + 1)}
          className="p-1.5 rounded hover:bg-sidebar-hover disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Далее"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </nav>
    </div>
  );
}

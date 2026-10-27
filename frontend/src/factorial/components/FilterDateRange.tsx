import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import {
  format,
  parse,
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  isSameMonth,
  isSameDay,
  isWithinInterval,
  addMonths,
  subMonths,
  isAfter,
} from 'date-fns';
import { ru } from 'date-fns/locale';
import { cn } from '@/factorial/lib/cn';

interface FilterDateRangeProps {
  from: string; // ISO yyyy-MM-dd or ''
  to: string;
  onChange: (from: string, to: string) => void;
}

/**
 * Factorial "Дата создания" filter — single month calendar with range selection:
 * two synced DD/MM/YYYY inputs on top, range highlight (start/end filled, middle tinted),
 * and a "Clear" link. First click sets start, second sets end (auto-orders).
 */
export default function FilterDateRange({ from, to, onChange }: FilterDateRangeProps) {
  const [month, setMonth] = useState<Date>(() => (from ? parse(from, 'yyyy-MM-dd', new Date()) : new Date()));

  const fromDate = from ? parse(from, 'yyyy-MM-dd', new Date()) : null;
  const toDate = to ? parse(to, 'yyyy-MM-dd', new Date()) : null;

  const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 });
  const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 });
  const days = eachDayOfInterval({ start, end });
  const weekdays = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

  const handleDay = (d: Date) => {
    const iso = format(d, 'yyyy-MM-dd');
    // No start yet, or both already set → start a new range
    if (!fromDate || (fromDate && toDate)) {
      onChange(iso, '');
      return;
    }
    // Have start, picking end
    if (isAfter(d, fromDate)) {
      onChange(from, iso);
    } else {
      onChange(iso, from); // clicked before start → swap
    }
  };

  const inRange = (d: Date) =>
    fromDate && toDate && isWithinInterval(d, { start: fromDate, end: toDate });

  const isEndpoint = (d: Date) =>
    (fromDate && isSameDay(d, fromDate)) || (toDate && isSameDay(d, toDate));

  const fmtInput = (dt: Date | null) => (dt ? format(dt, 'dd/MM/yyyy') : '');

  return (
    <div className="flex flex-col h-full">
      {/* Two synced date inputs */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <input
          type="text"
          readOnly
          value={fmtInput(fromDate)}
          placeholder="дд/мм/гггг"
          className="px-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm focus:outline-none"
        />
        <input
          type="text"
          readOnly
          value={fmtInput(toDate)}
          placeholder="дд/мм/гггг"
          className="px-3 py-2 rounded-fx-lg border border-card-border-soft bg-white text-fx-sm focus:outline-none"
        />
      </div>

      {/* Calendar */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-fx-sm font-medium">{format(month, 'LLLL yyyy', { locale: ru })} г.</span>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setMonth(subMonths(month, 1))} className="p-1 rounded-full border border-card-border-soft hover:bg-sidebar-hover" aria-label="Предыдущий месяц">
            <ChevronLeft className="w-4 h-4 text-text-muted" />
          </button>
          <button type="button" onClick={() => setMonth(addMonths(month, 1))} className="p-1 rounded-full border border-card-border-soft hover:bg-sidebar-hover" aria-label="Следующий месяц">
            <ChevronRight className="w-4 h-4 text-text-muted" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-y-1 text-center text-fx-xs text-text-muted/70 mb-1">
        {weekdays.map((w) => (
          <div key={w} className="py-1">{w}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-y-1">
        {days.map((d) => {
          const dim = !isSameMonth(d, month);
          const endpoint = isEndpoint(d);
          const middle = inRange(d) && !endpoint;
          return (
            <button
              key={format(d, 'yyyy-MM-dd')}
              type="button"
              onClick={() => handleDay(d)}
              className={cn(
                'h-9 text-fx-sm flex items-center justify-center transition-colors',
                middle && 'bg-teal-50',
                endpoint && 'bg-teal-500 text-white font-medium rounded-full',
                !endpoint && !middle && !dim && 'hover:bg-sidebar-hover rounded-full text-text-primary',
                dim && 'text-text-muted/40',
              )}
            >
              {format(d, 'd')}
            </button>
          );
        })}
      </div>

      {/* Clear link */}
      <div className="mt-auto pt-3 flex justify-end">
        <button
          type="button"
          onClick={() => onChange('', '')}
          className="text-fx-sm text-text-secondary hover:text-text-primary"
        >
          Clear
        </button>
      </div>
    </div>
  );
}

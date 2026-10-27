import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  format,
  parse,
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  isSameMonth,
  isToday,
  isSameDay,
  isBefore,
  isAfter,
  isValid,
  startOfDay,
  addMonths,
  subMonths,
} from 'date-fns';
import { ru } from 'date-fns/locale';
import { cn } from '@/factorial/lib/cn';

interface DatePickerFactorialProps {
  /** Selected date in ISO format (YYYY-MM-DD) or empty. */
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** If true, dates before today are disabled (cannot be clicked). */
  disablePast?: boolean;
  /**
   * If true, dates AFTER today are disabled + forward navigation is blocked.
   * Use for birth dates (нельзя родиться в будущем).
   */
  disableFuture?: boolean;
}

const MONTH_LABELS = [
  'янв', 'фев', 'мар', 'апр', 'май', 'июн',
  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
];

/**
 * Безопасный разбор значения даты. Ждём 'yyyy-MM-dd', но старые кандидаты могут
 * нести что угодно: ISO-datetime ("1995-03-15T00:00:00"), число из extra_data
 * (PDF-автозаполнение пишет поля числами) или мусор. ВСЕГДА возвращаем валидный
 * Date либо null — никогда Invalid Date, иначе format() кидает «RangeError:
 * Invalid time value» и форма редактирования падает целиком.
 */
function safeParseDate(value: unknown): Date | null {
  if (value == null || value === '') return null;
  const v = String(value);
  // Пробуем ожидаемый формат и распространённый русский dd.MM.yyyy.
  for (const fmt of ['yyyy-MM-dd', 'dd.MM.yyyy']) {
    const d = parse(v, fmt, new Date());
    if (isValid(d)) return d;
  }
  const native = new Date(v); // ловит ISO-datetime и прочие распознаваемые форматы
  return isValid(native) ? native : null;
}

/**
 * Custom date picker matching Factorial's design:
 * - Button shows 📅 icon + "DD MMM YYYY"
 * - Click → popup calendar with «месяц 2026 г.» header
 * - Header is CLICKABLE: день → выбор месяца → выбор года (быстрый прыжок на
 *   нужный год, напр. дата рождения)
 * - `disableFuture` блокирует будущие даты + стрелку «вперёд» (даты рождения)
 * - Smart positioning: opens UP if not enough space below
 * - Russian weekday labels (пн вт ср чт пт сб вс), Mon-first
 * - Today highlighted with light teal circle, selected with darker teal fill
 */
export default function DatePickerFactorial({
  value,
  onChange,
  placeholder = 'дд.мм.гггг',
  disablePast = false,
  disableFuture = false,
}: DatePickerFactorialProps) {
  const [open, setOpen] = useState(false);
  // 'days' (сетка дней) → 'months' (12 месяцев) → 'years' (блок из 12 лет).
  const [view, setView] = useState<'days' | 'months' | 'years'>('days');
  // Координаты поповера во вьюпорте — он рендерится ПОРТАЛОМ в body (position: fixed),
  // чтобы overflow/z-index родителя (модалка кандидата, скролл-контейнер) его не резал
  // и он не «уходил за текстурки».
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const [currentMonth, setCurrentMonth] = useState<Date>(() => {
    const parsed = safeParseDate(value);
    if (parsed) return parsed;
    // Пустая дата рождения: открывать календарь на ТЕКУЩЕМ месяце бессмысленно —
    // почти все дни там заблокированы disableFuture (это будущее), и с первого
    // взгляда кажется, что весь календарь сломан/некликабелен. Стартуем сразу с
    // разумного «типичного взрослого» года — от него до факта проще долистать.
    if (disableFuture) {
      const d = new Date();
      d.setFullYear(d.getFullYear() - 25);
      return d;
    }
    return new Date();
  });
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  // Каждое открытие начинаем с сетки дней.
  useEffect(() => {
    if (open) setView('days');
  }, [open]);

  // Позиционирование при открытии + слежение за скроллом/ресайзом, пока открыт.
  useEffect(() => {
    if (!open) { setCoords(null); return; }
    const place = () => {
      if (!buttonRef.current) return;
      const rect = buttonRef.current.getBoundingClientRect();
      const popupHeight = 344;
      const popupWidth = 280;
      const spaceBelow = window.innerHeight - rect.bottom;
      const openAbove = spaceBelow < popupHeight && rect.top > spaceBelow;
      const top = openAbove ? rect.top - popupHeight - 4 : rect.bottom + 4;
      const left = Math.min(rect.left, window.innerWidth - popupWidth - 8);
      setCoords({ top: Math.max(8, top), left: Math.max(8, left) });
    };
    place();
    window.addEventListener('scroll', place, true);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('scroll', place, true);
      window.removeEventListener('resize', place);
    };
  }, [open]);

  // Close on outside click (учитываем и кнопку, и портал-поповер).
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!containerRef.current?.contains(t) && !popupRef.current?.contains(t)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const selectedDate = safeParseDate(value);
  const displayLabel = selectedDate ? format(selectedDate, 'd MMM yyyy', { locale: ru }) : '';

  const start = startOfWeek(startOfMonth(currentMonth), { weekStartsOn: 1 });
  const end = endOfWeek(endOfMonth(currentMonth), { weekStartsOn: 1 });
  const days = eachDayOfInterval({ start, end });
  const weekdays = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

  const today = startOfDay(new Date());
  const todayYear = today.getFullYear();
  const todayMonth = today.getMonth();
  const curYear = currentMonth.getFullYear();
  const curMonth = currentMonth.getMonth();
  // Блок из 12 лет, в который попадает текущий год (для сетки годов).
  const yearBlockStart = curYear - (((curYear % 12) + 12) % 12);

  const isDisabled = (day: Date) =>
    (disablePast && isBefore(day, today)) || (disableFuture && isAfter(day, today));

  // Можно ли листать «вперёд» в текущем view (для дат рождения — нет в будущее).
  const canGoForward = (() => {
    if (!disableFuture) return true;
    if (view === 'days') return isBefore(startOfMonth(currentMonth), startOfMonth(today));
    if (view === 'months') return curYear < todayYear;
    return yearBlockStart + 11 < todayYear;
  })();

  const monthDisabled = (m: number) =>
    disableFuture && (curYear > todayYear || (curYear === todayYear && m > todayMonth));
  const yearDisabled = (y: number) => disableFuture && y > todayYear;

  const handleDayClick = (day: Date) => {
    if (isDisabled(day)) return;
    onChange(format(day, 'yyyy-MM-dd'));
    setOpen(false);
  };

  const goPrev = () => {
    if (view === 'days') setCurrentMonth(subMonths(currentMonth, 1));
    else if (view === 'months') setCurrentMonth(new Date(curYear - 1, curMonth, 1));
    else setCurrentMonth(new Date(curYear - 12, curMonth, 1));
  };
  const goNext = () => {
    if (!canGoForward) return;
    if (view === 'days') setCurrentMonth(addMonths(currentMonth, 1));
    else if (view === 'months') setCurrentMonth(new Date(curYear + 1, curMonth, 1));
    else setCurrentMonth(new Date(curYear + 12, curMonth, 1));
  };

  const headerLabel =
    view === 'days'
      ? `${format(currentMonth, 'LLLL yyyy', { locale: ru })} г.`
      : view === 'months'
        ? `${curYear} г.`
        : `${yearBlockStart} — ${yearBlockStart + 11}`;

  const headerClick = () => {
    if (view === 'days') setView('months');
    else if (view === 'months') setView('years');
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'w-full inline-flex items-center gap-2 px-3 py-2 rounded-fx-lg border bg-white text-fx-sm text-text-primary hover:bg-sidebar-hover focus:outline-none focus:border-border-hover',
          open ? 'border-primary' : 'border-card-border-soft'
        )}
      >
        <CalendarIcon className="w-4 h-4 text-text-muted shrink-0" strokeWidth={1.5} />
        <span className={cn(!displayLabel && 'text-text-muted')}>{displayLabel || placeholder}</span>
      </button>

      {open && coords && createPortal(
        <div
          ref={popupRef}
          onMouseDown={(e) => e.stopPropagation()}
          style={{ position: 'fixed', top: coords.top, left: coords.left, zIndex: 9999 }}
          className="bg-white rounded-card shadow-card-hover border border-card-border-soft p-3 w-[280px]"
        >
          {/* Header — кликабельный заголовок переключает день→месяц→год */}
          <div className="flex items-center justify-between mb-2">
            <button
              type="button"
              onClick={headerClick}
              disabled={view === 'years'}
              className={cn(
                'text-fx-sm font-medium px-1.5 py-0.5 rounded transition-colors',
                view !== 'years' && 'hover:bg-sidebar-hover cursor-pointer',
                view === 'years' && 'cursor-default'
              )}
            >
              {headerLabel}
            </button>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={goPrev}
                className="p-1 rounded hover:bg-sidebar-hover"
                aria-label="Назад"
              >
                <ChevronLeft className="w-4 h-4 text-text-muted" />
              </button>
              <button
                type="button"
                onClick={goNext}
                disabled={!canGoForward}
                className={cn(
                  'p-1 rounded',
                  canGoForward ? 'hover:bg-sidebar-hover' : 'opacity-30 cursor-not-allowed'
                )}
                aria-label="Вперёд"
              >
                <ChevronRight className="w-4 h-4 text-text-muted" />
              </button>
            </div>
          </div>

          {/* Days view */}
          {view === 'days' && (
            <>
              <div className="grid grid-cols-7 gap-1 mb-1">
                {weekdays.map((wd) => (
                  <div key={wd} className="text-[11px] text-text-muted/70 text-center py-1">
                    {wd}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {days.map((d) => {
                  const inMonth = isSameMonth(d, currentMonth);
                  const isSelected = selectedDate && isSameDay(d, selectedDate);
                  const isCurrentToday = isToday(d);
                  const disabled = isDisabled(d);
                  return (
                    <button
                      type="button"
                      key={format(d, 'yyyy-MM-dd')}
                      onClick={() => handleDayClick(d)}
                      disabled={disabled}
                      className={cn(
                        'w-9 h-9 rounded-full text-fx-sm flex items-center justify-center transition-colors',
                        disabled && 'text-text-muted/40 cursor-not-allowed',
                        !disabled && !inMonth && 'text-text-muted/40',
                        !disabled && inMonth && !isSelected && !isCurrentToday && 'text-text-primary hover:bg-sidebar-hover',
                        !disabled && inMonth && isCurrentToday && !isSelected && 'bg-teal-50 text-teal-700 font-medium',
                        isSelected && 'bg-teal-500 text-white font-medium'
                      )}
                    >
                      {format(d, 'd')}
                    </button>
                  );
                })}
              </div>
            </>
          )}

          {/* Months view */}
          {view === 'months' && (
            <div className="grid grid-cols-3 gap-2 py-1">
              {MONTH_LABELS.map((label, m) => {
                const isSelectedMonth =
                  selectedDate &&
                  selectedDate.getFullYear() === curYear &&
                  selectedDate.getMonth() === m;
                const disabled = monthDisabled(m);
                return (
                  <button
                    type="button"
                    key={label}
                    disabled={disabled}
                    onClick={() => {
                      setCurrentMonth(new Date(curYear, m, 1));
                      setView('days');
                    }}
                    className={cn(
                      'h-10 rounded-fx-lg text-fx-sm flex items-center justify-center transition-colors capitalize',
                      disabled && 'text-text-muted/40 cursor-not-allowed',
                      !disabled && isSelectedMonth && 'bg-teal-500 text-white font-medium',
                      !disabled && !isSelectedMonth && 'text-text-primary hover:bg-sidebar-hover'
                    )}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          )}

          {/* Years view */}
          {view === 'years' && (
            <div className="grid grid-cols-3 gap-2 py-1">
              {Array.from({ length: 12 }, (_, i) => yearBlockStart + i).map((y) => {
                const isSelectedYear = selectedDate && selectedDate.getFullYear() === y;
                const disabled = yearDisabled(y);
                return (
                  <button
                    type="button"
                    key={y}
                    disabled={disabled}
                    onClick={() => {
                      setCurrentMonth(new Date(y, curMonth, 1));
                      setView('months');
                    }}
                    className={cn(
                      'h-10 rounded-fx-lg text-fx-sm flex items-center justify-center transition-colors',
                      disabled && 'text-text-muted/40 cursor-not-allowed',
                      !disabled && isSelectedYear && 'bg-teal-500 text-white font-medium',
                      !disabled && !isSelectedYear && 'text-text-primary hover:bg-sidebar-hover'
                    )}
                  >
                    {y}
                  </button>
                );
              })}
            </div>
          )}
        </div>,
        document.body
      )}
    </div>
  );
}

import { useState, useEffect, useCallback } from 'react';
import {
  Calendar,
  Check,
  X,
  Clock,
  ChevronLeft,
  ChevronRight,
  Palmtree,
  ThermometerSun,
  Coffee,
  HelpCircle,
} from 'lucide-react';
import clsx from 'clsx';
import * as timeoffApi from '@/services/api/timeoff';
import type { TimeOffRequest, TimeOffCalendarEntry } from '@/services/api/timeoff';

// ============================================================
// CONSTANTS
// ============================================================

const TYPE_LABELS: Record<string, string> = {
  vacation: 'Отпуск',
  day_off: 'Отгул',
  sick_leave: 'Больничный',
  other: 'Другое',
};

const TYPE_ICONS: Record<string, typeof Palmtree> = {
  vacation: Palmtree,
  day_off: Coffee,
  sick_leave: ThermometerSun,
  other: HelpCircle,
};

const TYPE_COLORS: Record<string, string> = {
  vacation: 'bg-emerald-500/80',
  day_off: 'bg-blue-500/80',
  sick_leave: 'bg-amber-500/80',
  other: 'bg-purple-500/80',
};

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-amber-500/15', text: 'text-amber-400', label: 'Ожидает' },
  approved: { bg: 'bg-emerald-500/15', text: 'text-emerald-400', label: 'Одобрено' },
  rejected: { bg: 'bg-red-500/15', text: 'text-red-400', label: 'Отклонено' },
};

const FILTERS = [
  { value: '', label: 'Все' },
  { value: 'pending', label: 'Ожидает' },
  { value: 'approved', label: 'Одобрено' },
  { value: 'rejected', label: 'Отклонено' },
];

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

const DAY_NAMES = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

// ============================================================
// HELPERS
// ============================================================

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
  });
}

function formatDateRange(from: string, to: string): string {
  return `${formatDate(from)} — ${formatDate(to)}`;
}

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'только что';
  if (diffMin < 60) return `${diffMin} мин назад`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} ч назад`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD} дн назад`;
  return formatDate(dateStr);
}

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfWeek(year: number, month: number): number {
  const day = new Date(year, month, 1).getDay();
  // Convert from Sunday=0 to Monday=0
  return day === 0 ? 6 : day - 1;
}

function isDateInRange(date: Date, from: string, to: string): boolean {
  const d = date.getTime();
  const f = new Date(from).setHours(0, 0, 0, 0);
  const t = new Date(to).setHours(23, 59, 59, 999);
  return d >= f && d <= t;
}

// ============================================================
// CALENDAR VIEW COMPONENT
// ============================================================

function CalendarView({
  calendarData,
  currentMonth,
  onPrevMonth,
  onNextMonth,
}: {
  calendarData: TimeOffCalendarEntry[];
  currentMonth: Date;
  onPrevMonth: () => void;
  onNextMonth: () => void;
}) {
  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfWeek(year, month);

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  const getEntriesForDay = (day: number) => {
    const date = new Date(year, month, day);
    return calendarData.filter(
      (e) => e.status === 'approved' && isDateInRange(date, e.date_from, e.date_to)
    );
  };

  const today = new Date();
  const isToday = (day: number) =>
    year === today.getFullYear() && month === today.getMonth() && day === today.getDate();

  return (
    <div>
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={onPrevMonth}
          className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors text-white/40 hover:text-white/70"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h3 className="text-sm font-semibold text-white">
          {MONTH_NAMES[month]} {year}
        </h3>
        <button
          onClick={onNextMonth}
          className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors text-white/40 hover:text-white/70"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Day headers */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {DAY_NAMES.map((d) => (
          <div
            key={d}
            className="text-center text-[10px] uppercase tracking-wider text-white/20 py-1"
          >
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {cells.map((day, idx) => {
          if (day === null) {
            return <div key={`empty-${idx}`} className="h-20" />;
          }

          const entries = getEntriesForDay(day);
          const isWeekend = (firstDay + day - 1) % 7 >= 5;

          return (
            <div
              key={day}
              className={clsx(
                'h-20 rounded-lg border p-1 overflow-hidden transition-colors',
                isToday(day)
                  ? 'border-accent-500/30 bg-accent-500/5'
                  : isWeekend
                    ? 'border-white/[0.04] bg-white/[0.01]'
                    : 'border-white/[0.06] bg-white/[0.02]'
              )}
            >
              <span
                className={clsx(
                  'text-[11px] font-medium',
                  isToday(day) ? 'text-accent-400' : 'text-white/40'
                )}
              >
                {day}
              </span>
              <div className="mt-0.5 space-y-0.5">
                {entries.slice(0, 2).map((entry, i) => (
                  <div
                    key={`${entry.user_id}-${i}`}
                    className={clsx(
                      'text-[9px] text-white px-1 py-0.5 rounded truncate',
                      TYPE_COLORS[entry.type] || 'bg-purple-500/80'
                    )}
                    title={`${entry.user_name} — ${TYPE_LABELS[entry.type] || entry.type}`}
                  >
                    {entry.user_name?.split(' ')[0]}
                  </div>
                ))}
                {entries.length > 2 && (
                  <span className="text-[9px] text-white/30 pl-1">
                    +{entries.length - 2}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// REJECT MODAL
// ============================================================

function RejectModal({
  isOpen,
  onClose,
  onConfirm,
}: {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-dark-900 border border-white/10 rounded-2xl p-6 w-full max-w-md mx-4">
        <h3 className="text-sm font-semibold text-white mb-3">Причина отклонения</h3>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Укажите причину отклонения..."
          className="w-full h-24 bg-white/[0.05] border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder-white/20 focus:outline-none focus:border-accent-500/50 resize-none"
        />
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-white/50 hover:text-white/70 transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={() => {
              onConfirm(reason);
              setReason('');
            }}
            className="px-4 py-2 text-sm bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded-lg transition-colors"
          >
            Отклонить
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function TimeOffPage() {
  const [requests, setRequests] = useState<TimeOffRequest[]>([]);
  const [calendarData, setCalendarData] = useState<TimeOffCalendarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('');
  const [view, setView] = useState<'list' | 'calendar'>('list');
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [rejectModalId, setRejectModalId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    try {
      const data = await timeoffApi.getTimeOffRequests(filter || undefined);
      setRequests(data);
    } catch {
      setRequests([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const fetchCalendar = useCallback(async () => {
    try {
      const data = await timeoffApi.getTimeOffCalendar();
      setCalendarData(data);
    } catch {
      setCalendarData([]);
    }
  }, []);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  useEffect(() => {
    if (view === 'calendar') {
      fetchCalendar();
    }
  }, [view, fetchCalendar]);

  const handleApprove = async (id: number) => {
    setActionLoading(id);
    try {
      await timeoffApi.approveTimeOff(id);
      await fetchRequests();
    } catch {
      // silently ignore
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (id: number, reason: string) => {
    setActionLoading(id);
    setRejectModalId(null);
    try {
      await timeoffApi.rejectTimeOff(id, reason || undefined);
      await fetchRequests();
    } catch {
      // silently ignore
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="min-h-screen p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20">
            <Calendar className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white">Отпуска и отгулы</h1>
            <p className="text-[11px] text-white/30">Управление заявками на отсутствие</p>
          </div>
        </div>

        {/* View toggle */}
        <div className="flex items-center gap-1 bg-white/[0.04] rounded-xl p-1">
          <button
            onClick={() => setView('list')}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              view === 'list'
                ? 'bg-white/10 text-white'
                : 'text-white/30 hover:text-white/50'
            )}
          >
            Заявки
          </button>
          <button
            onClick={() => setView('calendar')}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              view === 'calendar'
                ? 'bg-white/10 text-white'
                : 'text-white/30 hover:text-white/50'
            )}
          >
            Календарь
          </button>
        </div>
      </div>

      {/* Calendar View */}
      {view === 'calendar' && (
        <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl p-4">
          <CalendarView
            calendarData={calendarData}
            currentMonth={currentMonth}
            onPrevMonth={() =>
              setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))
            }
            onNextMonth={() =>
              setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))
            }
          />
        </div>
      )}

      {/* List View */}
      {view === 'list' && (
        <>
          {/* Filters */}
          <div className="flex items-center gap-2 mb-4">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                  filter === f.value
                    ? 'bg-white/10 text-white'
                    : 'text-white/30 hover:text-white/50 bg-white/[0.02]'
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Loading */}
          {loading && (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin w-8 h-8 border-2 border-cyan-400 border-t-transparent rounded-full" />
            </div>
          )}

          {/* Empty */}
          {!loading && requests.length === 0 && (
            <div className="flex flex-col items-center py-16 text-center">
              <Calendar className="w-10 h-10 text-white/10 mb-3" />
              <p className="text-sm text-white/30">Нет заявок</p>
              <p className="text-xs text-white/15 mt-1">
                {filter ? 'Попробуйте изменить фильтр' : 'Заявки на отсутствие появятся здесь'}
              </p>
            </div>
          )}

          {/* Table */}
          {!loading && requests.length > 0 && (
            <div className="bg-white/[0.02] border border-white/[0.08] rounded-2xl overflow-hidden">
              {/* Table header */}
              <div className="grid grid-cols-[1fr_120px_160px_100px_140px] gap-2 px-4 py-2.5 text-[10px] uppercase tracking-wider text-white/20 border-b border-white/5">
                <span>Сотрудник</span>
                <span>Тип</span>
                <span>Даты</span>
                <span>Статус</span>
                <span>Действия</span>
              </div>

              {/* Table rows */}
              {requests.map((req) => {
                const TypeIcon = TYPE_ICONS[req.type] || HelpCircle;
                const status = STATUS_STYLES[req.status];
                const isActionable = req.status === 'pending';
                const isProcessing = actionLoading === req.id;

                return (
                  <div
                    key={req.id}
                    className="grid grid-cols-[1fr_120px_160px_100px_140px] gap-2 px-4 py-3 items-center border-b border-white/[0.04] last:border-b-0 hover:bg-white/[0.02] transition-colors"
                  >
                    {/* User */}
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500/30 to-blue-500/30 flex items-center justify-center border border-white/10 flex-shrink-0">
                        <span className="text-xs text-white/70 font-medium">
                          {req.user_name?.[0]?.toUpperCase() || '?'}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm text-white font-medium truncate">
                          {req.user_name || 'Без имени'}
                        </p>
                        <p className="text-[10px] text-white/20">{timeAgo(req.created_at)}</p>
                      </div>
                    </div>

                    {/* Type */}
                    <div className="flex items-center gap-2">
                      <TypeIcon className="w-3.5 h-3.5 text-white/30" />
                      <span className="text-xs text-white/50">
                        {TYPE_LABELS[req.type] || req.type}
                      </span>
                    </div>

                    {/* Dates */}
                    <span className="text-xs text-white/40">
                      {formatDateRange(req.date_from, req.date_to)}
                    </span>

                    {/* Status */}
                    <span
                      className={clsx(
                        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium w-fit',
                        status?.bg,
                        status?.text
                      )}
                    >
                      {req.status === 'pending' && <Clock className="w-3 h-3" />}
                      {req.status === 'approved' && <Check className="w-3 h-3" />}
                      {req.status === 'rejected' && <X className="w-3 h-3" />}
                      {status?.label}
                    </span>

                    {/* Actions */}
                    <div className="flex items-center gap-1.5">
                      {isActionable && !isProcessing && (
                        <>
                          <button
                            onClick={() => handleApprove(req.id)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors text-[11px] font-medium"
                          >
                            <Check className="w-3 h-3" />
                            Одобрить
                          </button>
                          <button
                            onClick={() => setRejectModalId(req.id)}
                            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors text-[11px] font-medium"
                          >
                            <X className="w-3 h-3" />
                            Отклонить
                          </button>
                        </>
                      )}
                      {isProcessing && (
                        <div className="animate-spin w-4 h-4 border-2 border-white/20 border-t-white/60 rounded-full" />
                      )}
                      {req.status === 'rejected' && req.reject_reason && (
                        <span
                          className="text-[10px] text-red-400/60 truncate max-w-[120px]"
                          title={req.reject_reason}
                        >
                          {req.reject_reason}
                        </span>
                      )}
                      {req.status === 'approved' && req.reviewer_name && (
                        <span className="text-[10px] text-white/20">
                          {req.reviewer_name}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Reject Modal */}
      <RejectModal
        isOpen={rejectModalId !== null}
        onClose={() => setRejectModalId(null)}
        onConfirm={(reason) => rejectModalId && handleReject(rejectModalId, reason)}
      />
    </div>
  );
}

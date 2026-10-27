import type { LeaveBalance } from '@/factorial/api/types';

/**
 * Два крупных счётчика отпуска:
 *  • Доступно  = сколько дней можно взять прямо сейчас (накоплено − использовано − на рассмотрении)
 *  • Накоплено = сколько заработано в текущем рабочем году (2 дня за каждый полный месяц, сброс на годовщине)
 * Плюс строка про рабочий год: до какой даты он идёт (неиспользованные дни сгорают на годовщине).
 * Данные — из /employees/{id}/leave-balance.
 */
export default function VacationCounters({
  balance,
  pendingDays = 0,
}: {
  balance?: LeaveBalance;
  pendingDays?: number;
}) {
  const accrued = balance?.vacation_total ?? 0;
  const used = balance?.vacation_used ?? 0;
  const available = Math.max(0, accrued - used - pendingDays);

  const cycleEndLabel = balance?.cycle_end
    ? new Date(balance.cycle_end).toLocaleDateString('ru-RU')
    : null;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-4">
        <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
          <p className="text-fx-xs uppercase tracking-wide text-text-muted mb-1">Доступно</p>
          <p className="font-bold text-emerald-600" style={{ fontSize: '2rem', lineHeight: 1 }}>
            {available}
            <span className="text-fx-base font-medium text-text-muted ml-1">дн.</span>
          </p>
          <p className="text-fx-xs text-text-muted mt-2">Можно взять прямо сейчас</p>
        </article>

        <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
          <p className="text-fx-xs uppercase tracking-wide text-text-muted mb-1">Накоплено</p>
          <p className="font-bold" style={{ fontSize: '2rem', lineHeight: 1 }}>
            {accrued}
            <span className="text-fx-base font-medium text-text-muted ml-1">дн.</span>
          </p>
          <p className="text-fx-xs text-text-muted mt-2">
            Накоплено в этом рабочем году · использовано {used}
            {pendingDays ? ` · на рассмотрении ${pendingDays}` : ''}
          </p>
        </article>
      </div>
      {cycleEndLabel && (
        <p className="text-fx-xs text-text-muted px-1">
          Рабочий год до {cycleEndLabel} · неиспользованные дни сгорают на годовщине
        </p>
      )}
    </div>
  );
}

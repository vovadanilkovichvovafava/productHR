import { differenceInCalendarDays } from 'date-fns';

function statusText(dateStr: string | null, doneLabel: string): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '—';
  const days = differenceInCalendarDays(d, new Date());
  return days <= 0 ? doneLabel : `через ${days} дн.`;
}

export default function EmployeeStatusCard({
  probationEndDate,
  oneYearDate,
}: {
  probationEndDate: string | null;
  oneYearDate: string | null;
}) {
  if (!probationEndDate && !oneYearDate) return null;
  return (
    <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
      <h2 className="font-semibold mb-4">Статус сотрудника</h2>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-fx-sm font-medium">{statusText(probationEndDate, 'Завершён')}</div>
          <div className="text-fx-xs text-text-muted mt-1">Испытательный срок</div>
        </div>
        <div>
          <div className="text-fx-sm font-medium">{statusText(oneYearDate, 'Достигнут')}</div>
          <div className="text-fx-xs text-text-muted mt-1">Год работы</div>
        </div>
      </div>
    </article>
  );
}

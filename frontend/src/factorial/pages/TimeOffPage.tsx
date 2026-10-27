import { useState } from 'react';
import { Palmtree as TreePalm } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import CalendarTemplate, { type CalendarEvent } from '@/factorial/templates/CalendarTemplate';
import RequestLeaveModal from '@/factorial/components/RequestLeaveModal';
import VacationCounters from '@/factorial/components/cabinet/VacationCounters';
import { getMyProfile, listLeaveRequests, getLeaveBalance } from '@/factorial/api/employees';
import { getAllTimeOff, type UnifiedTimeOff } from '@/factorial/api/timeoff';

const TYPE_COLOR: Record<string, string> = {
  vacation: '#16A34A',
  sick: '#DC2626',
  family_leave: '#2563EB',
  day_off: '#0EA5E9',
  bereavement: '#6B7280',
  other: '#6B7280',
};
const TYPE_LABEL: Record<string, string> = {
  vacation: 'Отпуск',
  sick: 'Больничный',
  family_leave: 'Семейные дни',
  day_off: 'Отгул',
  bereavement: 'По утрате',
  other: 'Другое',
};
const STATUS_LABEL: Record<string, string> = {
  pending: 'Ожидает',
  approved: 'Одобрено',
  rejected: 'Отклонено',
};

function fmt(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' });
}

export default function TimeOffPage() {
  const [open, setOpen] = useState(false);
  const { data: me } = useQuery({ queryKey: ['fx', 'me'], queryFn: getMyProfile });

  // Общий список всех отпусков (только admin/owner). 403 → isError → персональный вид.
  const allQ = useQuery({ queryKey: ['fx', 'timeoff', 'all'], queryFn: () => getAllTimeOff(), retry: false });
  const isAdmin = allQ.isSuccess && Array.isArray(allQ.data);
  const rows: UnifiedTimeOff[] = isAdmin ? (allQ.data as UnifiedTimeOff[]) : [];

  // Персональные заявки (System B) — для не-админа.
  const { data: myReqs = [] } = useQuery({
    queryKey: ['fx', 'leaves', 'mine'],
    queryFn: () => listLeaveRequests().catch(() => []),
    enabled: !isAdmin,
  });

  // Баланс текущего сотрудника для счётчиков «Доступно / Накоплено».
  const { data: balance } = useQuery({
    queryKey: ['fx', 'leave-balance', me?.id],
    queryFn: () => getLeaveBalance(me!.id),
    enabled: !!me,
  });
  const pendingVacationDays = myReqs
    .filter((r) => r.employee_id === me?.id && r.status === 'pending' && r.type === 'vacation')
    .reduce((s, r) => s + r.days, 0);

  const events: CalendarEvent[] = isAdmin
    ? rows
        .filter((r) => r.status !== 'rejected')
        .map((r, i) => ({
          id: i + 1,
          date: r.start,
          title: `${r.person_name || '—'}: ${r.type_label}${r.status === 'pending' ? ' (ожидает)' : ''}`,
          color: TYPE_COLOR[r.type] || '#6B7280',
        }))
    : me
      ? myReqs
          .filter((r) => r.employee_id === me.id)
          .map((r) => ({
            id: r.id,
            date: r.start_date,
            title: `${TYPE_LABEL[r.type] || r.type} (${r.days}д)`,
            color: TYPE_COLOR[r.type] || '#16A34A',
          }))
      : [];

  return (
    <>
      <CalendarTemplate
        breadcrumb={[{ label: 'Отпуска' }]}
        titleIcon={
          <div className="w-9 h-9 rounded-fx-lg bg-emerald-100 flex items-center justify-center">
            <TreePalm className="w-5 h-5 text-emerald-600" />
          </div>
        }
        title="Отпуска"
        events={events}
        primaryCta={{ label: 'Запросить отпуск', onClick: () => setOpen(true) }}
        headerExtra={me ? <VacationCounters balance={balance} pendingDays={pendingVacationDays} /> : undefined}
      />

      {isAdmin && (
        <div className="px-8 pb-8 -mt-2">
          <div className="bg-white rounded-card shadow-card border border-border overflow-hidden">
            <table className="w-full text-fx-sm">
              <thead className="text-text-muted border-b border-border">
                <tr>
                  <th className="text-left font-medium px-4 py-2.5">Сотрудник</th>
                  <th className="text-left font-medium px-4 py-2.5">Тип</th>
                  <th className="text-left font-medium px-4 py-2.5">Период</th>
                  <th className="text-left font-medium px-4 py-2.5">Дней</th>
                  <th className="text-left font-medium px-4 py-2.5">Статус</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.source}-${r.source_id}`} className="border-b border-card-border-soft last:border-0">
                    <td className="px-4 py-2.5">{r.person_name || '—'}</td>
                    <td className="px-4 py-2.5">{r.type_label}</td>
                    <td className="px-4 py-2.5">{fmt(r.start)} — {fmt(r.end)}</td>
                    <td className="px-4 py-2.5">{r.days}</td>
                    <td className="px-4 py-2.5">{STATUS_LABEL[r.status] || r.status}</td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-text-muted">Отпусков нет</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {open && me && <RequestLeaveModal employeeId={me.id} onClose={() => setOpen(false)} />}
    </>
  );
}

import { useState } from 'react';
import { User } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import ProfileTemplate from '@/factorial/templates/ProfileTemplate';
import { getLeaveBalance, listLeaveRequests } from '@/factorial/api/employees';
import { buildProfileTabs } from '@/factorial/lib/routes';
import { useProfileEmployee } from '@/factorial/lib/useProfileEmployee';
import { formatDateRu } from '@/factorial/lib/formatDate';
import LeaveBalanceCard from '@/factorial/components/cabinet/LeaveBalanceCard';
import VacationCounters from '@/factorial/components/cabinet/VacationCounters';
import RequestLeaveModal from '@/factorial/components/RequestLeaveModal';
import type { LeaveRequest } from '@/factorial/api/types';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <User className="w-5 h-5 text-pink-600" />
  </div>
);

const TYPE_LABELS: Record<string, string> = {
  vacation: 'Отпуск',
  sick: 'Больничный',
  family_leave: 'Семейные дни',
  bereavement: 'Отпуск по утрате',
};

const STATUS: Record<string, { label: string; cls: string }> = {
  pending: { label: 'На рассмотрении', cls: 'bg-amber-100 text-amber-700' },
  approved: { label: 'Одобрено', cls: 'bg-green-100 text-green-700' },
  rejected: { label: 'Отклонено', cls: 'bg-red-100 text-red-700' },
};

function RequestRow({ r }: { r: LeaveRequest }) {
  const st = STATUS[r.status] || { label: r.status, cls: 'bg-gray-100 text-gray-600' };
  return (
    <div className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-fx-sm font-medium truncate">{TYPE_LABELS[r.type] || r.type}</p>
        <p className="text-fx-xs text-text-muted">
          {formatDateRu(r.start_date)} — {formatDateRu(r.end_date)} · {r.days} дн.
        </p>
      </div>
      <span className={`shrink-0 px-2 py-1 rounded-pill text-fx-xs font-medium ${st.cls}`}>{st.label}</span>
    </div>
  );
}

export default function ProfilePlanningPage() {
  const { data: me, isError, byId, employeeId } = useProfileEmployee();
  const base = byId ? `/factorial/employees/${employeeId}` : '/factorial/profile';
  const { data: balance } = useQuery({
    queryKey: ['fx', 'leave-balance', me?.id],
    queryFn: () => getLeaveBalance(me!.id),
    enabled: !!me,
  });
  const { data: allReq = [] } = useQuery({
    queryKey: ['fx', 'leave-requests'],
    queryFn: () => listLeaveRequests(),
    enabled: !!me,
  });
  const [requestOpen, setRequestOpen] = useState(false);

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const mine = allReq
    .filter((r) => r.employee_id === me?.id)
    .sort((a, b) => (a.start_date < b.start_date ? 1 : -1));
  const upcoming = mine.filter((r) => new Date(r.end_date) >= today);
  const past = mine.filter((r) => new Date(r.end_date) < today);
  const pending = mine.filter((r) => r.status === 'pending').length;
  const pendingVacationDays = mine
    .filter((r) => r.status === 'pending' && r.type === 'vacation')
    .reduce((s, r) => s + r.days, 0);

  return (
    <ProfileTemplate
      breadcrumb={byId ? [{ label: 'Сотрудники', href: '/factorial/employees' }, { label: me?.user_name || 'Профиль' }] : [{ label: 'Профиль' }, { label: 'Планирование' }]}
      titleIcon={TITLE_ICON}
      title={byId ? (me?.user_name || 'Профиль') : 'Профиль'}
      subNav={buildProfileTabs(base)}
      leftColumn={
        isError ? (
          <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-6 text-fx-sm text-text-muted">
            Профиль сотрудника ещё не заведён. Обратитесь к HR.
          </article>
        ) : (
          <>
            <VacationCounters balance={balance} pendingDays={pendingVacationDays} />
            <LeaveBalanceCard balance={balance} onRequest={() => setRequestOpen(true)} />

            <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5 space-y-3">
              <h2 className="font-semibold">Ближайшие отсутствия</h2>
              {upcoming.length === 0 ? (
                <p className="text-fx-sm text-text-muted py-2">Запланированных отпусков нет.</p>
              ) : (
                <div className="divide-y divide-card-border-soft">
                  {upcoming.map((r) => (
                    <RequestRow key={r.id} r={r} />
                  ))}
                </div>
              )}
            </article>

            <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5 space-y-3">
              <h2 className="font-semibold">История</h2>
              {past.length === 0 ? (
                <p className="text-fx-sm text-text-muted py-2">Прошлых заявок нет.</p>
              ) : (
                <div className="divide-y divide-card-border-soft">
                  {past.map((r) => (
                    <RequestRow key={r.id} r={r} />
                  ))}
                </div>
              )}
            </article>

            {requestOpen && me && <RequestLeaveModal employeeId={me.id} onClose={() => setRequestOpen(false)} />}
          </>
        )
      }
      rightDetails={[
        { label: 'Доступно отпуска', value: <span>{balance ? `${balance.vacation_remaining} дн.` : '—'}</span> },
        { label: 'Больничных доступно', value: <span>{balance ? `${balance.sick_remaining} дн.` : '—'}</span> },
        { label: 'Заявок на рассмотрении', value: <span>{pending}</span> },
      ]}
    />
  );
}

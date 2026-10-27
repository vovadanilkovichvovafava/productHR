import { Users } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import PageHeader from '@/factorial/components/PageHeader';
import EmptyState from '@/factorial/components/EmptyState';
import DetailRow from '@/factorial/components/cabinet/DetailRow';
import { listMyReports } from '@/factorial/api/employees';
import { getErrorDetail } from '@/utils';
import { formatDateRu } from '@/factorial/lib/formatDate';
import type { Employee } from '@/factorial/api/types';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <Users className="w-5 h-5 text-pink-600" />
  </div>
);

// Руководителю — рабочие данные подчинённого. Паспорт, адрес и реквизиты сервер
// ему не отдаёт: это персональные данные для HR-администраторов.
function ReportCard({ e }: { e: Employee }) {
  const ex = (e.extra_data || {}) as Record<string, unknown>;
  const s = (v: unknown) => (v ? String(v) : '—');
  const dat = (v: unknown) => (v ? formatDateRu(v as string) : '—');
  const fio = (ex.full_name as string) || [ex.last_name, ex.first_name, ex.middle_name].filter(Boolean).join(' ') || e.user_name || '—';

  return (
    <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
      <div className="mb-2">
        <h2 className="font-semibold">{fio}</h2>
        <p className="text-fx-xs text-text-muted">{s(e.position)} · {s(e.department_name)}</p>
      </div>
      <DetailRow label="Дата начала работы" value={dat(e.department_start_date)} />
      <DetailRow label="Телефон" value={s(e.phone)} />
      <DetailRow label="Telegram" value={s(e.telegram_username)} />
      <DetailRow label="Экстренный контакт" value={`${s(ex.emergency_contact_name)} · ${s(ex.emergency_contact_phone)}`} />
    </article>
  );
}

export default function MyTeamPage() {
  // Раньше подчинённые брались из списка всех сотрудников — он только для
  // админов, и у руководителя-сотрудника всегда было «Нет подчинённых».
  const reportsQ = useQuery({ queryKey: ['fx', 'my-reports'], queryFn: listMyReports });
  const reports = reportsQ.data ?? [];

  return (
    <>
      <PageHeader breadcrumb={[{ label: 'Моя команда' }]} />
      <div className="px-8 py-6 space-y-5">
        <div className="flex items-center gap-2">
          {TITLE_ICON}
          <h1 className="text-fx-xl font-semibold">Моя команда</h1>
        </div>

        {reportsQ.isError ? (
          <div className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-12 text-center text-fx-sm text-red-600">
            {getErrorDetail(reportsQ.error, 'Не удалось загрузить команду')}
          </div>
        ) : reportsQ.isLoading ? null : reports.length === 0 ? (
          <div className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-12">
            <EmptyState emoji="👥" heading="Нет подчинённых" description="Здесь появятся сотрудники, у которых вы — руководитель." />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-[1200px]">
            {reports.map((e) => (
              <ReportCard key={e.id} e={e} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

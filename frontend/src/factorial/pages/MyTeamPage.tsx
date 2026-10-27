import { Users } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import PageHeader from '@/factorial/components/PageHeader';
import EmptyState from '@/factorial/components/EmptyState';
import DetailRow from '@/factorial/components/cabinet/DetailRow';
import { getMyProfile, listEmployees, getEmployeePassport } from '@/factorial/api/employees';
import { getOrgChart } from '@/factorial/api/orgUnits';
import { formatDateRu } from '@/factorial/lib/formatDate';
import type { Employee } from '@/factorial/api/types';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <Users className="w-5 h-5 text-pink-600" />
  </div>
);

async function downloadPassport(id: number) {
  try {
    const p = await getEmployeePassport(id);
    const a = document.createElement('a');
    a.href = `data:${p.content_type || 'application/octet-stream'};base64,${p.data_base64}`;
    a.download = p.filename || 'passport';
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch {
    alert('Не удалось скачать паспорт (нет доступа или файл не загружен).');
  }
}

function ReportCard({ e }: { e: Employee }) {
  const ex = (e.extra_data || {}) as Record<string, unknown>;
  const s = (v: unknown) => (v ? String(v) : '—');
  const dat = (v: unknown) => (v ? formatDateRu(v as string) : '—');
  const fio = (ex.full_name as string) || [ex.last_name, ex.first_name, ex.middle_name].filter(Boolean).join(' ') || e.user_name || '—';
  const hasPassport = ex.passport != null;

  return (
    <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
      <div className="flex items-center justify-between mb-2">
        <div>
          <h2 className="font-semibold">{fio}</h2>
          <p className="text-fx-xs text-text-muted">{s(e.position)} · {s(e.department_name)}</p>
        </div>
        {hasPassport ? (
          <button
            type="button"
            onClick={() => downloadPassport(e.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover shrink-0"
          >
            Скачать скан паспорта
          </button>
        ) : (
          <span className="text-fx-xs text-text-muted shrink-0">Паспорт не загружен</span>
        )}
      </div>
      <DetailRow label="Дата рождения" value={dat(ex.birth_date)} />
      <DetailRow label="№ паспорта" value={s(ex.passport_number)} />
      <DetailRow label="Кем выдан" value={s(ex.passport_issued_by)} />
      <DetailRow label="Дата выдачи" value={dat(ex.passport_issued)} />
      <DetailRow label="Адрес" value={s(ex.address)} />
      <DetailRow label="Телефон" value={s(e.phone)} />
      <DetailRow label="Экстренный контакт" value={`${s(ex.emergency_contact_name)} · ${s(ex.emergency_contact_phone)}`} />
    </article>
  );
}

export default function MyTeamPage() {
  const { data: me } = useQuery({ queryKey: ['fx', 'me'], queryFn: getMyProfile, retry: false });
  const { data: chart } = useQuery({ queryKey: ['fx', 'org-chart'], queryFn: getOrgChart });
  const { data: allEmps = [] } = useQuery({ queryKey: ['fx', 'employees', 'table'], queryFn: () => listEmployees(true) });

  const reportIds = new Set((chart?.people ?? []).filter((p) => me && p.manager_id === me.id).map((p) => p.id));
  const reports = allEmps.filter((e) => reportIds.has(e.id));

  return (
    <>
      <PageHeader breadcrumb={[{ label: 'Моя команда' }]} />
      <div className="px-8 py-6 space-y-5">
        <div className="flex items-center gap-2">
          {TITLE_ICON}
          <h1 className="text-fx-xl font-semibold">Моя команда</h1>
        </div>

        {reports.length === 0 ? (
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

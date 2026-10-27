import { useState, FormEvent } from 'react';
import { Briefcase } from 'lucide-react';
import { ColumnDef } from '@tanstack/react-table';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import TableTemplate from '@/factorial/templates/TableTemplate';
import { getVacancies, createVacancy } from '@/services/api/vacancies';
import type { Vacancy, VacancyStatus } from '@/types';

const NAV = [
  { label: 'Сотрудники', href: '/factorial/employees', end: true },
  { label: 'Команды', href: '/factorial/employees/teams' },
  { label: 'Оргсхема', href: '/factorial/employees/org-chart' },
  { label: 'Вакансии', href: '/factorial/employees/vacancies' },
];

const STATUS_LABEL: Record<string, string> = {
  draft: 'Черновик', open: 'Открыта', paused: 'На паузе', closed: 'Закрыта', cancelled: 'Отменена',
};
const STATUS_COLOR: Record<string, string> = {
  draft: 'text-slate-500', open: 'text-emerald-600', paused: 'text-amber-600', closed: 'text-slate-400', cancelled: 'text-rose-600',
};

function CreateVacancyModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ title: '', location: '', employment_type: '', salary_min: '', salary_max: '', status: 'open' });
  const [err, setErr] = useState('');

  const m = useMutation({
    mutationFn: () =>
      createVacancy({
        title: f.title,
        location: f.location || undefined,
        employment_type: f.employment_type || undefined,
        salary_min: f.salary_min ? Number(f.salary_min) : undefined,
        salary_max: f.salary_max ? Number(f.salary_max) : undefined,
        status: f.status as VacancyStatus,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['fx', 'vacancies'] }); onClose(); },
    onError: () => setErr('Не удалось создать вакансию (нужны права администратора).'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErr('');
    if (!f.title.trim()) { setErr('Укажите название.'); return; }
    m.mutate();
  };

  return (
    <div className="fx-modal-overlay" onClick={onClose}>
      <form className="fx-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Новая вакансия</h3>
        <div className="fx-field"><label>Название*</label><input className="fx-input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Frontend-разработчик" /></div>
        <div className="fx-field"><label>Локация</label><input className="fx-input" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} placeholder="Москва / Удалённо" /></div>
        <div className="fx-field"><label>Тип занятости</label><input className="fx-input" value={f.employment_type} onChange={(e) => setF({ ...f, employment_type: e.target.value })} placeholder="Полная" /></div>
        <div className="fx-field" style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}><label>З/п от</label><input className="fx-input" type="number" value={f.salary_min} onChange={(e) => setF({ ...f, salary_min: e.target.value })} /></div>
          <div style={{ flex: 1 }}><label>до</label><input className="fx-input" type="number" value={f.salary_max} onChange={(e) => setF({ ...f, salary_max: e.target.value })} /></div>
        </div>
        <div className="fx-field"><label>Статус</label>
          <select className="fx-select" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
            <option value="open">Открыта</option>
            <option value="draft">Черновик</option>
            <option value="paused">На паузе</option>
            <option value="closed">Закрыта</option>
          </select>
        </div>
        {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
        <div className="fx-modal-actions">
          <button type="button" className="fx-btn fx-btn--secondary" onClick={onClose}>Отмена</button>
          <button type="submit" className="fx-btn fx-btn--primary" disabled={m.isPending}>{m.isPending ? 'Создание…' : 'Создать'}</button>
        </div>
      </form>
    </div>
  );
}

export default function EmployeesVacanciesPage() {
  const { data: vacancies = [] } = useQuery({ queryKey: ['fx', 'vacancies'], queryFn: () => getVacancies() });
  const [creating, setCreating] = useState(false);

  const columns: ColumnDef<Vacancy, any>[] = [
    { accessorKey: 'title', header: 'Название' },
    { accessorKey: 'department_name', header: 'Отдел', cell: ({ getValue }) => (getValue() as string) || '—' },
    { accessorKey: 'location', header: 'Локация', cell: ({ getValue }) => (getValue() as string) || '—' },
    { accessorKey: 'employment_type', header: 'Тип', cell: ({ getValue }) => (getValue() as string) || '—' },
    {
      accessorKey: 'status',
      header: 'Статус',
      cell: ({ getValue }) => { const s = getValue() as string; return <span className={STATUS_COLOR[s] || ''}>{STATUS_LABEL[s] || s}</span>; },
    },
    { accessorKey: 'applications_count', header: 'Откликов' },
    {
      id: 'salary',
      header: 'З/п',
      cell: ({ row }) => {
        const v = row.original;
        if (!v.salary_min && !v.salary_max) return '—';
        return `${v.salary_min || ''}${v.salary_max ? '–' + v.salary_max : ''} ${v.salary_currency || ''}`.trim();
      },
    },
  ];

  return (
    <>
      <TableTemplate
        breadcrumb={[{ label: 'Сотрудники', href: '/factorial/employees' }, { label: 'Вакансии' }]}
        titleIcon={
          <div className="w-9 h-9 rounded-fx-lg bg-violet-100 flex items-center justify-center">
            <Briefcase className="w-5 h-5 text-violet-600" />
          </div>
        }
        title="Вакансии"
        secondaryNav={NAV}
        toolbar={{ searchKey: 'title', searchPlaceholder: 'Поиск вакансии...', primaryCta: { label: 'Создать вакансию', onClick: () => setCreating(true) } }}
        columns={columns}
        data={vacancies}
        emptyState={{ emoji: '💼', heading: 'Вакансий пока нет', description: 'Создайте первую вакансию кнопкой «Создать вакансию».' }}
      />
      {creating && <CreateVacancyModal onClose={() => setCreating(false)} />}
    </>
  );
}

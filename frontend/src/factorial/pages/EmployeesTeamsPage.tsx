import { Users } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';
import UserAvatar from '@/factorial/components/UserAvatar';
import { getOrgChart } from '@/factorial/api/orgUnits';

const NAV = [
  { label: 'Сотрудники', href: '/factorial/employees', end: true },
  { label: 'Команды', href: '/factorial/employees/teams' },
  { label: 'Оргсхема', href: '/factorial/employees/org-chart' },
];

export default function EmployeesTeamsPage() {
  const { data, isLoading } = useQuery({ queryKey: ['fx', 'org-chart'], queryFn: getOrgChart });
  const units = data?.units ?? [];

  return (
    <>
      <PageHeader breadcrumb={[{ label: 'Сотрудники', href: '/factorial/employees' }, { label: 'Команды' }]} />
      <div className="px-8 py-6 space-y-5">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
            <Users className="w-5 h-5 text-pink-600" />
          </div>
          <h1 className="text-fx-xl font-semibold">Команды</h1>
        </div>
        <SecondaryNav items={NAV} />
        {isLoading ? (
          <div className="text-fx-sm text-text-muted">Загрузка…</div>
        ) : units.length === 0 ? (
          <div className="text-fx-sm text-text-muted">
            Команд пока нет — создайте отделы в разделе «Оргсхема», и они появятся здесь.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {units.map((u) => (
              <div
                key={u.id}
                className="rounded-card border border-card-border-soft bg-card-translucent shadow-card p-4"
                style={{ borderTop: `3px solid ${u.color || '#94A3B8'}` }}
              >
                <div className="font-semibold text-fx-base">{u.name}</div>
                <div className="text-fx-xs text-text-muted mb-3">{u.employees.length} сотрудн.</div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {u.employees.length === 0 && <span className="text-fx-xs text-text-muted">Нет сотрудников</span>}
                  {u.employees.slice(0, 8).map((e) => (
                    <div key={e.id} title={e.user_name || ''}>
                      <UserAvatar fullName={e.user_name || '—'} size="sm" singleLetter />
                    </div>
                  ))}
                  {u.employees.length > 8 && (
                    <span className="text-fx-xs text-text-muted self-center">+{u.employees.length - 8}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

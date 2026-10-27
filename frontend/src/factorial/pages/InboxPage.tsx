import { useLocation } from 'react-router-dom';
import { Inbox, SlidersHorizontal, CalendarClock, PartyPopper, type LucideIcon } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import PageHeader from '@/factorial/components/PageHeader';
import SecondaryNav from '@/factorial/components/SecondaryNav';
import EmptyState from '@/factorial/components/EmptyState';
import InboxFilterPanel from '@/factorial/components/InboxFilterPanel';
import { getReminders } from '@/factorial/api/employees';
import { formatDateRu } from '@/factorial/lib/formatDate';
import type { Reminder } from '@/factorial/api/types';

const META: Record<Reminder['type'], { label: string; icon: LucideIcon; bg: string; fg: string }> = {
  probation_ending: { label: 'Конец испытательного срока', icon: CalendarClock, bg: 'bg-amber-100', fg: 'text-amber-600' },
  one_year_anniversary: { label: 'Годовщина — 1 год в компании', icon: PartyPopper, bg: 'bg-violet-100', fg: 'text-violet-600' },
};

function ReminderCard({ r }: { r: Reminder }) {
  const meta = META[r.type] || { label: r.type, icon: CalendarClock, bg: 'bg-gray-100', fg: 'text-gray-500' };
  const Icon = meta.icon;
  const soon = r.days_remaining <= 3;
  return (
    <div className="flex items-center gap-3 p-4 bg-white border border-card-border-soft rounded-card shadow-card">
      <div className={`w-9 h-9 rounded-fx-lg ${meta.bg} flex items-center justify-center shrink-0`}>
        <Icon className={`w-5 h-5 ${meta.fg}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-fx-sm font-medium truncate">{meta.label}</p>
        <p className="text-fx-xs text-text-muted">
          {r.employee_name} · {formatDateRu(r.date)}
        </p>
      </div>
      <span
        className={`shrink-0 px-2 py-1 rounded-pill text-fx-xs font-medium ${
          soon ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-text-muted'
        }`}
      >
        через {r.days_remaining} дн.
      </span>
    </div>
  );
}

export default function InboxPage() {
  const loc = useLocation();
  const tab = loc.pathname.endsWith('/completed') ? 'completed' : 'todo';
  const { data: reminders = [] } = useQuery({ queryKey: ['fx', 'reminders'], queryFn: getReminders, retry: false });
  const sorted = [...reminders].sort((a, b) => a.days_remaining - b.days_remaining);
  const count = tab === 'todo' ? sorted.length : 0;

  return (
    <>
      <PageHeader breadcrumb={[{ label: 'Входящие' }]} />
      <div className="px-8 py-6 space-y-5">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-fx-lg bg-red-100 flex items-center justify-center">
            <Inbox className="w-5 h-5 text-red-600" />
          </div>
          <h1 className="text-fx-xl font-semibold">Входящие</h1>
        </div>

        <SecondaryNav
          items={[
            { label: 'Задачи', href: '/inbox/todo' },
            { label: 'Завершено', href: '/inbox/completed' },
          ]}
        />

        <div className="space-y-3">
          <h2 className="text-fx-base font-semibold">
            {tab === 'todo' ? `Напоминания${count ? ` · ${count}` : ''}` : 'Завершено'}
          </h2>
          <div className="flex items-center justify-between">
            <InboxFilterPanel />
            <button
              type="button"
              onClick={() => alert('Demo mode — настройки')}
              className="w-9 h-9 rounded-fx-lg border border-card-border-soft bg-white flex items-center justify-center hover:bg-sidebar-hover"
              title="Настройки"
              aria-label="Настройки"
            >
              <SlidersHorizontal className="w-4 h-4 text-text-muted" />
            </button>
          </div>
        </div>

        {tab === 'todo' && sorted.length > 0 ? (
          <div className="space-y-2.5 max-w-3xl">
            {sorted.map((r) => (
              <ReminderCard key={`${r.type}-${r.employee_id}`} r={r} />
            ))}
          </div>
        ) : (
          <EmptyState
            emoji="☕️"
            heading="Отличная работа!"
            description={
              tab === 'todo'
                ? 'Нет напоминаний — испытательные сроки и годовщины под контролем.'
                : 'Здесь будут завершённые сообщения.'
            }
          />
        )}
      </div>
    </>
  );
}

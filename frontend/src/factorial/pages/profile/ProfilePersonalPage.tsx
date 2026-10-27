import { useState } from 'react';
import { User, Pencil } from 'lucide-react';
import ProfileTemplate from '@/factorial/templates/ProfileTemplate';
import { formatDateRu } from '@/factorial/lib/formatDate';
import { buildProfileTabs } from '@/factorial/lib/routes';
import { useProfileEmployee } from '@/factorial/lib/useProfileEmployee';
import DetailRow from '@/factorial/components/cabinet/DetailRow';
import PassportCard from '@/factorial/components/PassportCard';
import EmployeeEditModal from '@/factorial/components/EmployeeEditModal';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <User className="w-5 h-5 text-pink-600" />
  </div>
);

export default function ProfilePersonalPage() {
  const { data: me, isError, byId, employeeId } = useProfileEmployee();
  const base = byId ? `/factorial/employees/${employeeId}` : '/factorial/profile';
  const [editOpen, setEditOpen] = useState(false);

  const e = (me?.extra_data || {}) as Record<string, unknown>;
  const str = (v: unknown) => (v ? String(v) : '—');
  const dat = (v: unknown) => (v ? formatDateRu(v as string) : '—');
  const fio =
    (e.full_name as string) ||
    [e.last_name, e.first_name, e.middle_name].filter(Boolean).join(' ') ||
    '—';
  const methodLabel: Record<string, string> = { card: 'Карта', crypto: 'Криптокошелёк', bank: 'Банковский счёт', other: 'Другое' };
  const payMethod = e.payment_method ? (methodLabel[String(e.payment_method)] || String(e.payment_method)) : '—';
  const passportMeta = e.passport as { filename?: string; uploaded_at?: string } | undefined;

  return (
    <ProfileTemplate
      breadcrumb={byId ? [{ label: 'Сотрудники', href: '/factorial/employees' }, { label: me?.user_name || 'Профиль' }] : [{ label: 'Профиль' }, { label: 'Личные данные' }]}
      titleIcon={TITLE_ICON}
      title={byId ? (me?.user_name || 'Профиль') : 'Профиль'}
      subNav={buildProfileTabs(base)}
      leftColumn={
        isError ? (
          <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-6 text-fx-sm text-text-muted">
            Профиль сотрудника ещё не заведён.
          </article>
        ) : (
          <>
            <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-semibold">Личные данные</h2>
                <button
                  type="button"
                  onClick={() => setEditOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
                >
                  <Pencil className="w-3.5 h-3.5" /> Изменить
                </button>
              </div>
              <DetailRow label="ФИО" value={fio} />
              <DetailRow label="Дата рождения" value={dat(e.birth_date)} />
              <DetailRow label="№ паспорта" value={str(e.passport_number)} />
              <DetailRow label="Кем выдан" value={str(e.passport_issued_by)} />
              <DetailRow label="Дата выдачи" value={dat(e.passport_issued)} />
              <DetailRow label="Адрес" value={str(e.address)} />
              <DetailRow label="Телефон" value={str(me?.phone)} />
              <DetailRow label="Telegram" value={str(me?.telegram_username)} />
              <DetailRow label="Способ выплаты" value={payMethod} />
              <DetailRow label="Реквизиты" value={str(e.payment_details)} />
              <p className="text-fx-xs text-text-muted mt-3">Данные можете заполнить вы или HR. Ниже можно загрузить скан паспорта.</p>
            </article>
            <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
              <h2 className="font-semibold mb-2">Контакт для экстренной связи</h2>
              <DetailRow label="Имя" value={str(e.emergency_contact_name)} />
              <DetailRow label="Телефон" value={str(e.emergency_contact_phone)} />
              <p className="text-fx-xs text-text-muted mt-3">Можете заполнить вы или HR (кнопка «Изменить»).</p>
            </article>
            <PassportCard passport={passportMeta} />
            {editOpen && <EmployeeEditModal {...(byId ? { employeeId } : { selfMode: true })} section="personal" onClose={() => setEditOpen(false)} onSaved={() => setEditOpen(false)} />}
          </>
        )
      }
      rightDetails={[
        { label: 'Электронная почта', value: <span>{me?.user_email || '—'}</span> },
        { label: 'Отдел', value: <span>{me?.department_name || '—'}</span> },
      ]}
    />
  );
}

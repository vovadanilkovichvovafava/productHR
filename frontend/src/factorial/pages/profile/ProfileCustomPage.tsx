import { User } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import ProfileTemplate from '@/factorial/templates/ProfileTemplate';
import { getMyProfile } from '@/factorial/api/employees';
import { CABINET_TABS } from '@/factorial/lib/routes';
import DetailRow from '@/factorial/components/cabinet/DetailRow';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <User className="w-5 h-5 text-pink-600" />
  </div>
);

// Поля, которые уже показаны на других вкладках или намеренно скрыты (ИНН/СНИЛС).
const SHOWN_ELSEWHERE = new Set([
  'full_name', 'last_name', 'first_name', 'middle_name', 'birth_date',
  'passport_number', 'passport_issued_by', 'passport_issued', 'passport_issued_date', 'passport',
  'address', 'emergency_contact_name', 'emergency_contact_phone',
  'inn', 'snils',
]);

const LABELS: Record<string, string> = {
  wallet: 'Реквизиты',
  bank: 'Банк',
  bank_account: 'Банковский счёт',
  education: 'Образование',
  notes: 'Заметки',
  comment: 'Комментарий',
};

function humanize(k: string): string {
  if (LABELS[k]) return LABELS[k];
  const s = k.replace(/[_-]+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function ProfileCustomPage() {
  const { data: me, isError } = useQuery({ queryKey: ['fx', 'me'], queryFn: getMyProfile, retry: false });

  const e = (me?.extra_data || {}) as Record<string, unknown>;
  const rows = Object.keys(e)
    .filter((k) => !SHOWN_ELSEWHERE.has(k))
    .map((k) => ({ k, v: e[k] }))
    .filter(({ v }) => v != null && v !== '' && typeof v !== 'object')
    .map(({ k, v }) => ({ label: humanize(k), value: String(v) }));

  return (
    <ProfileTemplate
      breadcrumb={[{ label: 'Профиль' }, { label: 'Другое' }]}
      titleIcon={TITLE_ICON}
      title="Профиль"
      subNav={CABINET_TABS}
      leftColumn={
        isError ? (
          <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-6 text-fx-sm text-text-muted">
            Профиль сотрудника ещё не заведён. Обратитесь к HR.
          </article>
        ) : (
          <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5">
            <h2 className="font-semibold mb-2">Дополнительные поля</h2>
            {rows.length === 0 ? (
              <p className="text-fx-sm text-text-muted py-2">
                Дополнительных полей пока нет. Здесь появятся кастомные поля профиля, которые заполнит HR.
              </p>
            ) : (
              <>
                {rows.map((r) => (
                  <DetailRow key={r.label} label={r.label} value={r.value} />
                ))}
                <p className="text-fx-xs text-text-muted mt-3">Поля заполняет HR.</p>
              </>
            )}
          </article>
        )
      }
      rightDetails={[
        { label: 'Электронная почта', value: <span>{me?.user_email || '—'}</span> },
        { label: 'Отдел', value: <span>{me?.department_name || '—'}</span> },
      ]}
    />
  );
}

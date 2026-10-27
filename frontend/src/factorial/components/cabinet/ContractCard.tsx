import type { Employee } from '@/factorial/api/types';
import { formatDateRu, formatTenure } from '@/factorial/lib/formatDate';
import DetailRow from './DetailRow';

/** Карточка договора над списком документов («Соглашения»). Данные — из
 *  Employee того, чьи документы открыты: свой профиль или сотрудник в виде HR.
 *  До 27.10.2026 карточка сама грузила `/employees/me`, и HR в карточке
 *  сотрудника видел СВОЙ договор. */
export default function ContractCard({ employee: me }: { employee?: Employee | null }) {
  if (!me) return null; // нет карточки сотрудника — показываем только список документов

  const startRaw = me.department_start_date || me.practice_start_date || me.created_at || null;
  const start = startRaw ? `${formatDateRu(startRaw)} (${formatTenure(startRaw)} назад)` : '—';
  const fmt = (d?: string | null) => (d ? formatDateRu(d) : '—');
  const sign = (ok?: boolean, at?: string | null) => (ok ? `Подписан${at ? ' · ' + formatDateRu(at) : ''}` : 'Не подписан');

  return (
    <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-5 max-w-2xl">
      <h2 className="font-semibold mb-2">Договор</h2>
      <DetailRow label="Должность" value={me.position || '—'} />
      <DetailRow label="Дата начала" value={start} />
      <DetailRow label="Испытательный срок" value={me.probation_end_date ? `до ${fmt(me.probation_end_date)}` : '—'} />
      <DetailRow label="Статус договора" value={sign(me.contract_signed, me.contract_signed_at)} />
      <DetailRow label="NDA" value={sign(me.nda_signed, me.nda_signed_at)} />
      <DetailRow label="Год работы" value={fmt(me.one_year_date)} />
    </article>
  );
}

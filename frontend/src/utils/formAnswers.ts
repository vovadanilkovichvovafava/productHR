/**
 * Подписи и разбор адреса страницы «Анкеты → Ответы» (06.11.2026).
 * Чистые функции — под тестами (`__tests__/formAnswers.test.ts`).
 */
import type { FormAnswerItem, FormAnswerStatus, FormSendError } from '@/services/api/formAnswers';

export type StatusTab = FormAnswerStatus | 'all';

export const STATUS_TABS: { key: StatusTab; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'submitted', label: 'Заполнены' },
  { key: 'opened', label: 'Открыли, не отправили' },
  { key: 'sent', label: 'Не открыли' },
  { key: 'orphan', label: 'Без кандидата' },
];

export const PERIODS: { days: number | null; label: string }[] = [
  { days: null, label: 'За всё время' },
  { days: 7, label: 'За 7 дней' },
  { days: 30, label: 'За 30 дней' },
  { days: 90, label: 'За 90 дней' },
];

/** Сервер отдаёт время без пояса (UTC) — показываем местным. */
export function formatWhen(iso: string | null | undefined): string {
  if (!iso) return '';
  const norm = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(norm);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export type ChipTone = 'ok' | 'warn' | 'muted' | 'bad';

export function statusChip(item: Pick<FormAnswerItem, 'status' | 'opened_at' | 'submitted_at' | 'entity_name'>): { label: string; tone: ChipTone } {
  switch (item.status) {
    case 'submitted':
      return { label: `Заполнена ${formatWhen(item.submitted_at)}`.trim(), tone: 'ok' };
    case 'opened':
      return {
        label: item.opened_at ? `Открыта ${formatWhen(item.opened_at)}, не отправлена` : 'Открыта, не отправлена',
        tone: 'warn',
      };
    case 'orphan':
      // Карточка есть, но ответ в ней не виден — бывает реже, чем «карточки нет».
      return { label: item.entity_name ? 'Нет в карточке' : 'Без кандидата', tone: 'bad' };
    default:
      return { label: 'Не открыта', tone: 'muted' };
  }
}

/** Что случилось у кандидата при отправке — по отчёту его браузера. */
export function sendErrorText(err: FormSendError): string {
  const times = err.count && err.count > 1 ? ` (попыток: ${err.count})` : '';
  let what: string;
  switch (err.kind) {
    case 'network':
      what = 'не дошло до сервера (интернет или VPN)';
      break;
    case 'server_status':
      what = err.status ? `сервер ответил ошибкой ${err.status}` : 'сервер ответил ошибкой';
      break;
    case 'server_detail':
      what = err.message ? `сервер отказал: ${err.message}` : 'сервер отказал';
      break;
    case 'client':
      what = 'сбой в браузере кандидата';
      break;
    default:
      what = 'ошибка при отправке';
  }
  const when = formatWhen(err.at);
  return `Не отправилось${when ? ` ${when}` : ''}: ${what}${times}`;
}

export interface AnswerFilters {
  status: StatusTab;
  formId: number | null;
  sentBy: number | null;
  days: number | null;
  /** Открытый ответ: «d12» — ссылка, «s5» — ответ без ссылки. */
  open: { kind: 'dispatch' | 'orphan'; id: number } | null;
}

const toId = (v: string | null): number | null => {
  const n = Number(v);
  return v && Number.isInteger(n) && n > 0 ? n : null;
};

/** Состояние страницы из адреса: F5 оставляет на том же месте. Мусор — значения по умолчанию. */
export function parseAnswerFilters(params: URLSearchParams): AnswerFilters {
  const status = params.get('status');
  const days = toId(params.get('days'));
  const open = params.get('open') || '';
  const openId = toId(open.slice(1));
  return {
    status: STATUS_TABS.some((t) => t.key === status) ? (status as StatusTab) : 'all',
    formId: toId(params.get('form')),
    sentBy: toId(params.get('sender')),
    days: PERIODS.some((p) => p.days === days) ? days : null,
    open: openId && (open[0] === 'd' || open[0] === 's')
      ? { kind: open[0] === 'd' ? 'dispatch' : 'orphan', id: openId }
      : null,
  };
}

export function openKey(item: Pick<FormAnswerItem, 'kind' | 'id'>): string {
  return `${item.kind === 'dispatch' ? 'd' : 's'}${item.id}`;
}

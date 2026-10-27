import { format, formatDistanceToNow, intervalToDuration } from 'date-fns';
import { ru } from 'date-fns/locale';

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Дата из строки сервера. «YYYY-MM-DD» — это календарный день, а `new Date()`
 * читает такую строку как полночь по UTC: западнее Гринвича дата съезжала на
 * день назад («1 октября» показывалось как «30 сентября»). Такие строки
 * читаем как местную дату; остальное (с временем) — как раньше.
 */
export function parseDate(date: Date | string): Date {
  if (typeof date !== 'string') return date;
  const m = DATE_ONLY.exec(date.trim());
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return new Date(date);
}

export function formatDateRu(date: Date | string): string {
  const d = parseDate(date);
  if (Number.isNaN(d.getTime())) return '—';
  return format(d, 'd MMMM yyyy г.', { locale: ru });
}

export function formatRelativeRu(date: Date | string): string {
  const d = parseDate(date);
  if (Number.isNaN(d.getTime())) return '—';
  return formatDistanceToNow(d, { locale: ru, addSuffix: true });
}

export function formatShortDateRu(date: Date | string): string {
  const d = parseDate(date);
  if (Number.isNaN(d.getTime())) return '—';
  return format(d, 'dd.MM.yyyy');
}

/** Russian plural helper: pick form for n. */
function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

/**
 * Factorial-style "hired ago" relative text: no "около", correct Russian grammar.
 * e.g. "7 месяцев назад", "2 года назад", "3 месяца назад", "год назад".
 */
export function formatHiredAgo(date: Date | string, now: Date = new Date()): string {
  const d = parseDate(date);
  if (Number.isNaN(d.getTime())) return '—';
  // Дата выхода ещё впереди — это не «менее месяца назад».
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (d.getTime() > today.getTime() + 24 * 60 * 60 * 1000 - 1) return `выходит ${format(d, 'dd.MM.yyyy')}`;
  let months =
    (now.getFullYear() - d.getFullYear()) * 12 + (now.getMonth() - d.getMonth());
  if (now.getDate() < d.getDate()) months -= 1;
  if (months < 1) return 'менее месяца назад';
  if (months < 12) {
    return `${months} ${plural(months, 'месяц', 'месяца', 'месяцев')} назад`;
  }
  const years = Math.floor(months / 12);
  if (years === 1) return 'год назад';
  return `${years} ${plural(years, 'год', 'года', 'лет')} назад`;
}

/** Стаж в формате Factorial: «7 мес. 4 дн.» / «2 г. 3 мес.». */
export function formatTenure(start: Date | string, now: Date = new Date()): string {
  const s = parseDate(start);
  if (Number.isNaN(s.getTime()) || s.getTime() > now.getTime()) return '';
  const d = intervalToDuration({ start: s, end: now });
  const parts: string[] = [];
  if (d.years) parts.push(`${d.years} г.`);
  if (d.months) parts.push(`${d.months} мес.`);
  if (d.days && !d.years) parts.push(`${d.days} дн.`);
  return parts.length ? parts.join(' ') : 'менее дня';
}

/** «1 октября 2026 г. (7 мес. назад)»; будущая дата — «(ещё не вышел)». */
export function formatStartWithTenure(start: Date | string, now: Date = new Date()): string {
  const s = parseDate(start);
  if (Number.isNaN(s.getTime())) return '—';
  if (s.getTime() > now.getTime()) return `${formatDateRu(s)} (ещё не вышел)`;
  return `${formatDateRu(s)} (${formatTenure(s, now)} назад)`;
}

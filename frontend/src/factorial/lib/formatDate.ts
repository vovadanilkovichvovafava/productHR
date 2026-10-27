import { format, formatDistanceToNow, intervalToDuration } from 'date-fns';
import { ru } from 'date-fns/locale';

export function formatDateRu(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return format(d, 'd MMMM yyyy г.', { locale: ru });
}

export function formatRelativeRu(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return formatDistanceToNow(d, { locale: ru, addSuffix: true });
}

export function formatShortDateRu(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
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
export function formatHiredAgo(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  const now = new Date();
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
export function formatTenure(start: Date | string): string {
  const s = typeof start === 'string' ? new Date(start) : start;
  if (Number.isNaN(s.getTime())) return '';
  const d = intervalToDuration({ start: s, end: new Date() });
  const parts: string[] = [];
  if (d.years) parts.push(`${d.years} г.`);
  if (d.months) parts.push(`${d.months} мес.`);
  if (d.days && !d.years) parts.push(`${d.days} дн.`);
  return parts.length ? parts.join(' ') : 'менее дня';
}

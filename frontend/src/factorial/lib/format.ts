function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
}

export function fmtShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('ru-RU');
}

/** Human tenure since a start date, e.g. "1 год 2 месяца". */
export function tenure(iso: string | null | undefined): string {
  if (!iso) return '—';
  const start = new Date(iso);
  const now = new Date();
  if (isNaN(start.getTime()) || now < start) return '—';
  let months = (now.getFullYear() - start.getFullYear()) * 12 + (now.getMonth() - start.getMonth());
  if (now.getDate() < start.getDate()) months--;
  if (months < 1) return 'меньше месяца';
  const y = Math.floor(months / 12);
  const m = months % 12;
  const parts: string[] = [];
  if (y > 0) parts.push(`${y} ${plural(y, 'год', 'года', 'лет')}`);
  if (m > 0) parts.push(`${m} ${plural(m, 'месяц', 'месяца', 'месяцев')}`);
  return parts.join(' ') || 'меньше месяца';
}

export function daysWord(n: number): string {
  return `${n} ${plural(n, 'день', 'дня', 'дней')}`;
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?';
  const p = name.trim().split(/\s+/).filter(Boolean);
  const res = ((p[0]?.[0] || '') + (p[1]?.[0] || '')).toUpperCase();
  return res || '?';
}

/** True if the date is in the past (probation completed / anniversary passed). */
export function isPast(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  return !isNaN(d.getTime()) && d.getTime() < Date.now();
}

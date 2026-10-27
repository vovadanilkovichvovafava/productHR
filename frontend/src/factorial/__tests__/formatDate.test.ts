import { describe, it, expect } from 'vitest';
import { parseDate, formatShortDateRu, formatHiredAgo, formatTenure, formatStartWithTenure } from '../lib/formatDate';
import { fmtShort } from '../lib/format';

describe('parseDate', () => {
  it('YYYY-MM-DD — местная дата, без сдвига на день', () => {
    const d = parseDate('2026-10-01');
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 9, 1]);
    expect(formatShortDateRu('2026-10-01')).toBe('01.10.2026');
    expect(fmtShort('2026-10-01')).toBe(new Date(2026, 9, 1).toLocaleDateString('ru-RU'));
  });
  it('мусор — прочерк, а не исключение', () => {
    expect(formatShortDateRu('abc')).toBe('—');
  });
});

describe('formatHiredAgo', () => {
  const now = new Date(2026, 9, 27, 12, 0);
  it('прошлое', () => {
    expect(formatHiredAgo('2026-07-01', now)).toBe('3 месяца назад');
    expect(formatHiredAgo('2026-10-20', now)).toBe('менее месяца назад');
    expect(formatHiredAgo('2025-10-01', now)).toBe('год назад');
  });
  it('сегодня — ещё «менее месяца назад»', () => {
    expect(formatHiredAgo('2026-10-27', now)).toBe('менее месяца назад');
  });
  it('будущая дата — не «назад»', () => {
    expect(formatHiredAgo('2026-11-03', now)).toBe('выходит 03.11.2026');
  });
});

describe('formatTenure / formatStartWithTenure', () => {
  const now = new Date(2026, 9, 27, 12, 0);
  it('будущий выход', () => {
    expect(formatTenure('2026-11-03', now)).toBe('');
    expect(formatStartWithTenure('2026-11-03', now)).toBe('3 ноября 2026 г. (ещё не вышел)');
  });
  it('прошлый выход', () => {
    expect(formatStartWithTenure('2026-03-27', now)).toBe('27 марта 2026 г. (7 мес. назад)');
  });
});

import { describe, it, expect } from 'vitest';
import { matchesSearch, allVisibleSelected, toggleAllVisible } from '../lib/tableSelection';

const rows = [
  { id: 1, fullName: 'Иванов Пётр' },
  { id: 2, fullName: 'Петрова Анна' },
  { id: 3, fullName: 'Иванова Мария' },
];

describe('matchesSearch', () => {
  it('без запроса — все', () => {
    expect(rows.filter((r) => matchesSearch(r, 'fullName', ''))).toHaveLength(3);
  });
  it('по подстроке без учёта регистра', () => {
    expect(rows.filter((r) => matchesSearch(r, 'fullName', 'иванов')).map((r) => r.id)).toEqual([1, 3]);
  });
});

describe('«Выбрать всех» по найденным', () => {
  it('отмечает только видимые', () => {
    const visible = rows.filter((r) => matchesSearch(r, 'fullName', 'иванов')).map((r) => r.id);
    const next = toggleAllVisible(new Set(), visible);
    expect([...next].sort()).toEqual([1, 3]);
    expect(next.has(2)).toBe(false);
  });

  it('повторное нажатие снимает только видимые, скрытые отмеченные остаются', () => {
    const next = toggleAllVisible(new Set([1, 2, 3]), [1, 3]);
    expect([...next]).toEqual([2]);
  });

  it('частично отмеченные видимые — добавляет недостающие', () => {
    expect([...toggleAllVisible(new Set([1]), [1, 3])].sort()).toEqual([1, 3]);
  });

  it('пустая выдача — галочка не стоит', () => {
    expect(allVisibleSelected(new Set([1]), [])).toBe(false);
  });
});

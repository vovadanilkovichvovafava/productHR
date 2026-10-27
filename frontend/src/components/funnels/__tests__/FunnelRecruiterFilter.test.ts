import { describe, it, expect } from 'vitest';
import { funnelViewChips } from '../FunnelRecruiterFilter';
import { funnelViewKey } from '../useFunnelCandidates';

// Над воронкой — плашка на каждого отмеченного рекрутёра, с полным именем и
// крестиком (владелец, 21.10.2026).
describe('funnelViewChips', () => {
  const options = {
    total: 30,
    recruiters: [
      { user_id: 3, name: 'Мария', count: 0 },
      { user_id: 4, name: 'Влада', count: 12 },
      { user_id: 5, name: 'Пётр', count: 6 },
      { user_id: 6, name: 'Эльвира', count: 2 },
    ],
  };
  const labels = (owner: number[] | 'all', opts = options) =>
    funnelViewChips(owner, 3, opts).map((c) => c.label);

  it('каждый отмеченный — полным именем, вы первым с пометкой', () => {
    expect(labels([3])).toEqual(['Мария (вы)']);
    expect(labels([6, 4, 3, 5])).toEqual(['Мария (вы)', 'Влада', 'Пётр', 'Эльвира']);
  });
  it('все — одна плашка', () => {
    expect(labels('all')).toEqual(['Все рекрутёры']);
  });
  it('пока список не загрузился — без выдуманных имён', () => {
    expect(labels([3, 5], null)).toEqual(['Вы', '…']);
  });
});

describe('funnelViewKey', () => {
  it('порядок и повторы не важны — один и тот же выбор', () => {
    expect(funnelViewKey([5, 3, 5])).toBe(funnelViewKey([3, 5]));
    expect(funnelViewKey('all')).toBe('all');
  });
});

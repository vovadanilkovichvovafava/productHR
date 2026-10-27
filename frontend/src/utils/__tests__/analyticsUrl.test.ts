/**
 * «Аналитика» помнит отчёт и фильтры в адресе (Мария, 14.10.2026: «при
 * обновлении страницы остаёмся на той же странице»). Адрес — ввод снаружи,
 * поэтому главное здесь — что мусор и чужое в нём ничего не ломают.
 */
import { describe, it, expect } from 'vitest';

import { readAnalyticsState, writeAnalyticsParams } from '../analyticsUrl';

const ALL = [
  { id: 'vacancy', reports: [{ id: 'ttf' }, { id: 'funnel' }] },
  { id: 'recruiter', reports: [{ id: 'funnel-recruiter' }] },
  { id: 'sourcer', reports: [{ id: 'sourcers' }] },
];
const RECRUITER_VISIBLE = ALL.filter((c) => c.id !== 'recruiter');
const PERIODS = ['current', 'month', 'quarter', 'half_year', 'year'];
const STATUSES = ['open', 'all', 'closed'];

const read = (qs: string, cats = ALL) =>
  readAnalyticsState(new URLSearchParams(qs), cats, PERIODS, STATUSES);

describe('readAnalyticsState', () => {
  it('пустой адрес — значения по умолчанию', () => {
    expect(read('')).toEqual({
      category: 'vacancy',
      report: 'ttf',
      period: 'current',
      from: '',
      to: '',
      status: 'open',
      department: null,
    });
  });

  it('после F5 возвращается тот же отчёт с теми же фильтрами', () => {
    expect(read('cat=recruiter&report=funnel-recruiter&period=quarter&status=closed&dept=7')).toEqual({
      category: 'recruiter',
      report: 'funnel-recruiter',
      period: 'quarter',
      from: '',
      to: '',
      status: 'closed',
      department: 7,
    });
  });

  it('рекрутёру ссылка на админскую категорию открывает его «Вакансии»', () => {
    const s = read('cat=recruiter&report=funnel-recruiter&period=quarter', RECRUITER_VISIBLE);
    expect(s.category).toBe('vacancy');
    expect(s.report).toBe('ttf');
    // Нейтральные фильтры сохраняются — они не дают доступа ни к чему лишнему.
    expect(s.period).toBe('quarter');
  });

  it('отчёт из чужой категории не подхватывается', () => {
    expect(read('cat=vacancy&report=sourcers').report).toBe('ttf');
  });

  it('мусор в адресе не ломает страницу', () => {
    expect(read('period=forever&status=deleted&dept=abc&from=вчера&to=2026-13')).toMatchObject({
      period: 'current',
      status: 'open',
      department: null,
      from: '',
      to: '',
    });
  });

  it('свой период с датами сохраняется', () => {
    expect(read('period=custom&from=2026-09-01&to=2026-09-30')).toMatchObject({
      period: 'custom',
      from: '2026-09-01',
      to: '2026-09-30',
    });
  });
});

describe('writeAnalyticsParams', () => {
  it('значение по умолчанию из адреса убирается — ссылка короче', () => {
    const next = writeAnalyticsParams(new URLSearchParams('period=quarter&status=closed'), {
      period: 'current',
      status: 'open',
    });
    expect(next.toString()).toBe('');
  });

  it('чужие параметры адреса не трогает', () => {
    const next = writeAnalyticsParams(new URLSearchParams('foo=1'), { department: 5 });
    expect(next.get('foo')).toBe('1');
    expect(next.get('dept')).toBe('5');
  });

  it('категория и её отчёт пишутся одной правкой', () => {
    const next = writeAnalyticsParams(new URLSearchParams(''), {
      category: 'sourcer',
      report: 'sourcers',
    });
    expect(next.get('cat')).toBe('sourcer');
    expect(next.get('report')).toBe('sourcers');
  });

  it('подразделение «Все» (null) убирает ключ', () => {
    expect(writeAnalyticsParams(new URLSearchParams('dept=5'), { department: null }).has('dept')).toBe(false);
  });
});

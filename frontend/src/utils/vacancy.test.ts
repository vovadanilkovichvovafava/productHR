import { describe, expect, it } from 'vitest';
import type { Vacancy } from '@/types';
import { getVacancyExitOptions, isExplicitlyAssigned, isRequestVisibleTo, pinMovedCandidate } from './vacancy';

const ME = 3;
const vac = (over: Partial<Vacancy> & { accepted_by?: number[]; dismissed_by?: number[] }): Vacancy => {
  const { accepted_by, dismissed_by, ...rest } = over;
  return {
    id: 1,
    status: 'open',
    created_by: 99,
    assigned_to: [],
    assigned_to_all: false,
    extra_data: { accepted_by: accepted_by ?? [], dismissed_by: dismissed_by ?? [] },
    ...rest,
  } as unknown as Vacancy;
};

describe('isExplicitlyAssigned', () => {
  it('true only for an explicit assignee who has not dismissed it', () => {
    expect(isExplicitlyAssigned(vac({ assigned_to: [ME] }), ME)).toBe(true);
    expect(isExplicitlyAssigned(vac({ assigned_to: [ME], dismissed_by: [ME] }), ME)).toBe(false);
  });
  it('creator and «всем рекрутёрам» do not count', () => {
    expect(isExplicitlyAssigned(vac({ created_by: ME }), ME)).toBe(false);
    expect(isExplicitlyAssigned(vac({ assigned_to_all: true }), ME)).toBe(false);
  });
});

describe('isRequestVisibleTo — admin', () => {
  it('sees undistributed requests', () => {
    expect(isRequestVisibleTo(vac({ status: 'pending_review' }), ME, true)).toBe(true);
    expect(isRequestVisibleTo(vac({ status: 'draft' }), ME, true)).toBe(true);
  });
  it('sees an open vacancy assigned to them that someone else already took', () => {
    expect(isRequestVisibleTo(vac({ assigned_to: [4, ME], accepted_by: [4] }), ME, true)).toBe(true);
  });
  it('hides it once taken personally', () => {
    expect(isRequestVisibleTo(vac({ assigned_to: [4, ME], accepted_by: [4, ME] }), ME, true)).toBe(false);
  });
  it('does not surface vacancies they only created or that go to «всем рекрутёрам»', () => {
    expect(isRequestVisibleTo(vac({ created_by: ME, assigned_to: [4], accepted_by: [4] }), ME, true)).toBe(false);
    expect(isRequestVisibleTo(vac({ assigned_to_all: true, accepted_by: [4] }), ME, true)).toBe(false);
  });
});

describe('isRequestVisibleTo — recruiter', () => {
  it('sees an assigned vacancy until taking it', () => {
    expect(isRequestVisibleTo(vac({ assigned_to: [ME], accepted_by: [4] }), ME, false)).toBe(true);
    expect(isRequestVisibleTo(vac({ assigned_to: [ME], accepted_by: [ME] }), ME, false)).toBe(false);
  });
});

describe('getVacancyExitOptions', () => {
  const shared = vac({ created_by: 4, assigned_to: [4, ME], accepted_by: [4, ME] });
  const alone = vac({ created_by: ME, assigned_to: [ME], accepted_by: [ME] });
  it('recruiter in a shared vacancy can only leave', () => {
    expect(getVacancyExitOptions(shared, ME, false)).toMatchObject({ canLeave: true, canClose: false, others: [4] });
  });
  it('admin in a shared vacancy can both leave and close', () => {
    expect(getVacancyExitOptions(shared, ME, true)).toMatchObject({ canLeave: true, canClose: true });
  });
  it('the last participant can only close', () => {
    expect(getVacancyExitOptions(alone, ME, false)).toMatchObject({ canLeave: false, canClose: true });
    expect(getVacancyExitOptions(alone, ME, true)).toMatchObject({ canLeave: false, canClose: true });
  });
  it('a non-participant recruiter can neither leave nor close a vacancy others work in', () => {
    expect(getVacancyExitOptions(shared, 77, false)).toMatchObject({ canLeave: false, canClose: false });
  });
  it('a non-participant admin can only close', () => {
    expect(getVacancyExitOptions(shared, 77, true)).toMatchObject({ canLeave: false, canClose: true });
  });
});

describe('pinMovedCandidate — перемещённый кандидат остаётся во вкладке', () => {
  const a = { id: 1, stage: 'applied' };
  const b = { id: 2, stage: 'applied' };
  const moved = { id: 3, stage: 'phone_screen' }; // уехал из вкладки «Новый»
  const all = [a, b, moved];

  it('прикрепляет перемещённого первым, если он выпал из вкладки', () => {
    expect(pinMovedCandidate([a, b], all, 3)).toEqual([moved, a, b]);
  });

  it('ничего не меняет, если кандидат и так во вкладке', () => {
    const inTab = [a, b];
    expect(pinMovedCandidate(inTab, all, 1)).toBe(inTab);
  });

  it('без закрепления список не трогается', () => {
    const inTab = [a, b];
    expect(pinMovedCandidate(inTab, all, null)).toBe(inTab);
  });

  it('закреплённого уже нет в воронке (сняли) — список не ломается', () => {
    expect(pinMovedCandidate([a], [a], 999)).toEqual([a]);
  });
});

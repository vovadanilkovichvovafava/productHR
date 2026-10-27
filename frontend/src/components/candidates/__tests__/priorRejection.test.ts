import { describe, it, expect } from 'vitest';
import { priorRejectionLabel, priorRejectionWhere } from '../priorRejection';

// Подписи метки «Был отказ» (22.10.2026) — одни на список, воронку, карточку и окно добавления.
describe('priorRejection', () => {
  const year = new Date().getFullYear();

  it('строка списка: вид · дата · воронка', () => {
    expect(priorRejectionLabel({
      kind: 'rejected', source: 'funnel', entity_id: 1, vacancy_title: 'Трафик', date: `${year}-08-28T12:00:00`,
    })).toBe('Был отказ · 28 авг · Трафик');
    expect(priorRejectionLabel({
      kind: 'no_show', source: 'archive', entity_id: 1, vacancy_title: 'SMM', date: '2025-06-01T09:00:00',
    })).toBe('Не пришёл · июнь 2025 · SMM');
  });

  it('подробно: где, кто, с какого этапа; архив — статус ClickUp', () => {
    expect(priorRejectionWhere({
      kind: 'rejected', source: 'funnel', entity_id: 1, vacancy_title: 'Трафик',
      date: `${year}-08-28T12:00:00`, recruiter_name: 'Мария', from_stage: 'Выполняет ТЗ',
    })).toBe(`Отказ 28 августа ${year} г. · «Трафик» · рекрутёр Мария · с этапа «Выполняет ТЗ»`);
    expect(priorRejectionWhere({
      kind: 'rejected', source: 'archive', entity_id: 1, vacancy_title: 'UA', from_stage: 'собес (1): нет',
    })).toBe('Отказ · «UA» · ClickUp: собес (1): нет');
    expect(priorRejectionWhere({ kind: 'rejected', source: 'card', entity_id: 1 })).toBe('Отказ · вне воронок');
  });
});

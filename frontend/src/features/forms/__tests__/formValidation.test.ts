import { describe, expect, it } from 'vitest';
import type { FormField } from '@/services/api/forms';
import { cleanOptions, formProblem, normalizeFields } from '../formValidation';

const text = (label: string): FormField => ({ id: label, type: 'text', label, required: false });

describe('formValidation', () => {
  it('варианты без пустых и повторов', () => {
    expect(cleanOptions(['Да', ' да ', '', 'Нет', '  '])).toEqual(['Да', 'Нет']);
    expect(cleanOptions(undefined)).toEqual([]);
  });

  it('ловит то, на чём кандидат застрянет', () => {
    expect(formProblem('  ', [text('ФИО')])).toBe('Введите название анкеты');
    expect(formProblem('Анкета', [])).toBe('Добавьте хотя бы один вопрос');
    expect(formProblem('Анкета', [{ ...text(''), label: '  ' }])).toMatch(/впишите текст вопроса/);
    expect(formProblem('Анкета', [{ id: 'r', type: 'radio', label: 'Выбор', required: true, options: ['Да', 'да'] }]))
      .toMatch(/два разных варианта/);
    expect(formProblem('Анкета', [{ id: 's', type: 'scale', label: 'Шкала', required: true, min: 12, max: 10 }]))
      .toMatch(/меньше максимума/);
    expect(formProblem('Анкета', [{ id: 's', type: 'scale', label: 'Шкала', required: true, min: 0, max: 50 }]))
      .toMatch(/не больше 20/);
    expect(formProblem('Анкета', [text('ФИО')])).toBeNull();
  });

  it('шкала от нуля — допустима (раньше 0 подменялся единицей)', () => {
    expect(formProblem('Анкета', [{ id: 's', type: 'scale', label: 'Шкала', required: false, min: 0, max: 10 }])).toBeNull();
  });

  it('перед сохранением: текст без краёв, варианты почищены, границы шкалы целые', () => {
    const [q, s] = normalizeFields([
      { id: 'q', type: 'select', label: ' Город ', required: false, options: ['Минск', 'минск', ''] },
      { id: 's', type: 'scale', label: 'Шкала', required: false, min: 1.7, max: undefined },
    ]);
    expect(q.label).toBe('Город');
    expect(q.options).toEqual(['Минск']);
    expect([s.min, s.max]).toEqual([1, 10]);
  });
});

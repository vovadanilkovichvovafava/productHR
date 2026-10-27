import { describe, it, expect } from 'vitest';
import { changedFields, dateFieldToServer } from '../lib/employeePatch';

describe('changedFields', () => {
  const keys = ['phone', 'address', 'position'];

  it('нетронутые поля не отправляются', () => {
    expect(changedFields({ phone: '+375291234567', address: 'Минск' }, { phone: '+375291234567', address: 'Минск' }, keys)).toEqual({});
  });

  it('очищенное поле уходит как null, а не пропадает', () => {
    expect(changedFields({ address: 'Минск' }, { address: '   ' }, keys)).toEqual({ address: null });
  });

  it('изменённое — обрезанным значением', () => {
    expect(changedFields({ position: '' }, { position: ' Дизайнер ' }, keys)).toEqual({ position: 'Дизайнер' });
  });

  it('пробелы по краям — не изменение', () => {
    expect(changedFields({ phone: '123' }, { phone: '123 ' }, keys)).toEqual({});
  });
});

describe('dateFieldToServer', () => {
  it('дата и очистка', () => {
    expect(dateFieldToServer('2026-10-01')).toBe('2026-10-01T00:00:00');
    expect(dateFieldToServer(null)).toBeNull();
  });
});

import { describe, it, expect } from 'vitest';
import { formatPhone, isPhoneComplete } from '../lib/phone';

describe('formatPhone', () => {
  it('российский номер собирается в шаблон', () => {
    expect(formatPhone('79991234567')).toBe('+7 (999) 123-45-67');
    expect(formatPhone('+7 999 123 45 67')).toBe('+7 (999) 123-45-67');
    expect(formatPhone('89991234567')).toBe('+7 (999) 123-45-67');
  });

  it('казахстанский +7 7xx — тот же шаблон', () => {
    expect(formatPhone('+77011234567')).toBe('+7 (701) 123-45-67');
  });

  it('по мере набора', () => {
    expect(formatPhone('7')).toBe('+7');
    expect(formatPhone('+7 (99')).toBe('+7 (99');
    expect(formatPhone('+7 (999) 1')).toBe('+7 (999) 1');
    // одиночная «8» ещё не российский номер (может быть «80 29…»)
    expect(formatPhone('8')).toBe('8');
    expect(formatPhone('89')).toBe('+7 (9');
  });

  it('белорусский и узбекский номера не превращаются в +7 и не обрезаются', () => {
    expect(formatPhone('+375 29 123-45-67')).toBe('+375 29 123-45-67');
    expect(formatPhone('+375291234567')).toBe('+375291234567');
    expect(formatPhone('+998 90 123 45 67')).toBe('+998 90 123 45 67');
    expect(formatPhone('80 29 123 45 67')).toBe('80 29 123 45 67');
  });

  it('лишние цифры у +7 не отрезаются', () => {
    expect(formatPhone('+7 (999) 123-45-678')).toBe('+7 (999) 123-45-678');
  });

  it('посторонние символы убираются, плюс только первым', () => {
    expect(formatPhone('+375 (29) abc 123')).toBe('+375 (29) 123');
    expect(formatPhone('  ')).toBe('');
    expect(formatPhone('+')).toBe('+');
  });
});

describe('isPhoneComplete', () => {
  it('российский — 11 цифр', () => {
    expect(isPhoneComplete('+7 (999) 123-45-67')).toBe(true);
    expect(isPhoneComplete('+7 (999) 123-45')).toBe(false);
  });
  it('международный — 8–15 цифр', () => {
    expect(isPhoneComplete('+375 29 123-45-67')).toBe(true);
    expect(isPhoneComplete('+375 29')).toBe(false);
  });
});

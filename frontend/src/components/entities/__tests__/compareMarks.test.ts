import { describe, it, expect } from 'vitest';
import { matchKindOf, matchSide, type Side } from '../CandidateCompareCard';

// Отметки окна сравнения (22.10.2026): ✓ — совпадает, ≈ — похоже/частично.
const side = (over: Partial<Side>): Side => ({
  name: '', photo: '', position: '', company: '', phone: '', email: '', telegram: '', age: '',
  birthDate: '', city: '', salary: '', experience: '', source: '', tags: '', statusLabel: '',
  isRejected: false, rejectReason: '', rejectedAt: '', history: [], resumes: [], resumeText: '',
  resumeExtra: { experience: '', skills: '', languages: '', education: '' }, notes: [], ...over,
});

describe('отметки совпадений', () => {
  const a = side({ name: 'Демидова Алина', phone: '80291234567' });

  it('телефон в другом формате — ✓, если сервер счёл его тем же номером', () => {
    const b = side({ phone: '+375291234567' });
    const sig = [{ field: 'phone', label: 'Совпадение телефона', identity: true }];
    expect(matchKindOf(sig, 'phone', () => matchSide(a, b, 'phone'))).toBe('exact');
  });

  it('ФИО: отчество не мешает ✓, опечатка в имени — ≈', () => {
    const sig = [{ field: 'name', label: 'Совпадение имени', identity: true }];
    const same = side({ name: 'Демидова Алина Игоревна' });
    const typo = side({ name: 'Демидова Алиса' });
    expect(matchKindOf(sig, 'name', () => matchSide(a, same, 'name'))).toBe('exact');
    expect(matchKindOf(sig, 'name', () => matchSide(a, typo, 'name'))).toBe('partial');
  });

  it('косвенный признак при разных значениях — ≈; без признака — ничего', () => {
    const b = side({ phone: '+79161234567' });
    const soft = [{ field: 'phone', label: 'Последние 7 цифр', identity: false }];
    expect(matchKindOf(soft, 'phone', () => matchSide(a, b, 'phone'))).toBe('partial');
    expect(matchKindOf(soft, 'email', () => false)).toBe(null);
  });
});

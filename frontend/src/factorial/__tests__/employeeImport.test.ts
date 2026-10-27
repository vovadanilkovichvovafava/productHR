import { describe, it, expect } from 'vitest';
import { normalizeImportRows } from '../lib/employeeImport';

describe('normalizeImportRows', () => {
  it('числа из Excel становятся строками (иначе сервер отвечает 422)', () => {
    const [row] = normalizeImportRows([{ Email: 'a@b.c', 'Телефон': 79991234567, 'Паспорт №': 1234567 }]);
    expect(row.phone).toBe('79991234567');
    expect(row.passport_number).toBe('1234567');
  });

  it('дата-число Excel → ДД.ММ.ГГГГ', () => {
    const [row] = normalizeImportRows([{ Email: 'a@b.c', 'Дата начала (ДД.ММ.ГГГГ)': 46000 }]);
    expect(row.department_start_date).toBe('09.12.2025');
  });

  it('дата-объект → ДД.ММ.ГГГГ по местному календарю', () => {
    const [row] = normalizeImportRows([{ Email: 'a@b.c', 'Дата начала (ДД.ММ.ГГГГ)': new Date(2026, 0, 9) }]);
    expect(row.department_start_date).toBe('09.01.2026');
  });

  it('текст как есть, пустые ячейки и строки без email отбрасываются', () => {
    const rows = normalizeImportRows([
      { Email: ' a@b.c ', 'Имя': 'Анна', 'Фамилия': '' },
      { Email: '', 'Имя': 'Без почты' },
    ]);
    expect(rows).toEqual([{ email: 'a@b.c', first_name: 'Анна' }]);
  });
});

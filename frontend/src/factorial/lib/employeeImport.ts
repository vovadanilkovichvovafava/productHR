import * as XLSX from 'xlsx';

// Строки Excel → тело POST /employees/bulk-import.
//
// Сервер ждёт у всех полей СТРОКИ (BulkImportRow), а sheet_to_json отдаёт
// числа: телефон 79991234567 и дату (серийный номер Excel, 46000) — и весь
// файл падал с 422 «Input should be a valid string» (до 27.10.2026). Теперь
// каждая ячейка — строка, дата — ДД.ММ.ГГГГ (формат, который сервер понимает).
// raw:false не годится: дата пришла бы в формате ячейки (например «1/9/26»
// по-американски) и читалась бы неоднозначно.

export const IMPORT_COLUMNS: Record<string, string> = {
  'Email': 'email', 'Фамилия': 'last_name', 'Имя': 'first_name', 'Отчество': 'middle_name',
  'Должность': 'position', 'Телефон': 'phone', 'Telegram': 'telegram_username',
  'Дата начала (ДД.ММ.ГГГГ)': 'department_start_date', 'Адрес': 'address',
  'Паспорт №': 'passport_number', 'Способ выплаты': 'payment_method', 'Реквизиты': 'payment_details',
};

const DATE_KEYS = new Set(['department_start_date']);

const pad = (n: number) => String(n).padStart(2, '0');

function cellToString(key: string, v: unknown): string {
  if (v instanceof Date) {
    return `${pad(v.getDate())}.${pad(v.getMonth() + 1)}.${v.getFullYear()}`;
  }
  if (typeof v === 'number' && DATE_KEYS.has(key)) {
    const d = XLSX.SSF.parse_date_code(v);
    if (d && d.y) return `${pad(d.d)}.${pad(d.m)}.${d.y}`;
  }
  if (typeof v === 'number') {
    // Целые без экспоненты: 79991234567 → «79991234567».
    return Number.isInteger(v) ? v.toFixed(0) : String(v);
  }
  return String(v ?? '').trim();
}

export function normalizeImportRows(raw: Record<string, unknown>[]): Record<string, string>[] {
  return raw
    .map((r) => {
      const o: Record<string, string> = {};
      for (const [col, key] of Object.entries(IMPORT_COLUMNS)) {
        const v = r[col];
        if (v === undefined || v === null || v === '') continue;
        const s = cellToString(key, v);
        if (s) o[key] = s;
      }
      return o;
    })
    .filter((o) => o.email);
}

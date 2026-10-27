import { useState } from 'react';
import * as XLSX from 'xlsx';
import { useNavigate } from 'react-router-dom';
import { bulkImportEmployees, downloadEmployeeTemplate } from '@/factorial/api/employees';
import type { BulkImportResult } from '@/factorial/api/types';

const COLS: Record<string, string> = {
  'Email': 'email', 'Фамилия': 'last_name', 'Имя': 'first_name', 'Отчество': 'middle_name',
  'Должность': 'position', 'Телефон': 'phone', 'Telegram': 'telegram_username',
  'Дата начала (ДД.ММ.ГГГГ)': 'department_start_date', 'Адрес': 'address',
  'Паспорт №': 'passport_number', 'Способ выплаты': 'payment_method', 'Реквизиты': 'payment_details',
};

export default function EmployeesImportPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const downloadTemplate = () => { void downloadEmployeeTemplate(); };

  const onFile = async (file: File) => {
    setBusy(true); setResult(null); setErr('');
    try {
      const wb = XLSX.read(await file.arrayBuffer());
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
      const rows = raw.map((r) => {
        const o: Record<string, unknown> = {};
        for (const [col, key] of Object.entries(COLS)) if (r[col] !== undefined && r[col] !== '') o[key] = r[col];
        return o;
      }).filter((o) => o.email);
      setResult(await bulkImportEmployees(rows));
    } catch {
      setErr('Не удалось импортировать файл. Проверьте формат (xlsx) и колонки.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="factorial-root p-6 max-w-2xl">
      <h1 className="text-fx-lg font-semibold mb-1">Импорт сотрудников</h1>
      <p className="text-fx-sm text-text-muted mb-4">Скачайте шаблон, заполните и загрузите. Сопоставление по Email, существующие профили обновляются.</p>
      <div className="flex gap-3 mb-4">
        <button type="button" className="fx-btn fx-btn--secondary" onClick={downloadTemplate}>Скачать шаблон</button>
        <label className="fx-btn fx-btn--primary cursor-pointer">
          {busy ? 'Импорт…' : 'Загрузить xlsx'}
          <input type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.currentTarget.value = ''; }} />
        </label>
        <button type="button" className="fx-btn fx-btn--secondary" onClick={() => navigate('/factorial/employees')}>Назад</button>
      </div>
      {err && <div style={{ color: '#B91C1C', fontSize: 13 }}>{err}</div>}
      {result && (
        <div className="bg-card-translucent border border-card-border-soft rounded-card p-4 text-fx-sm space-y-1">
          <p>Обновлено: <b>{result.updated}</b></p>
          {result.skipped.length > 0 && <p className="text-text-muted">Не найдено по email ({result.skipped.length}): {result.skipped.join(', ')}</p>}
          {result.errors.length > 0 && <p style={{ color: '#B91C1C' }}>Ошибки: {result.errors.join('; ')}</p>}
        </div>
      )}
    </div>
  );
}

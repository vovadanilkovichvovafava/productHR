import { useState } from 'react';
import * as XLSX from 'xlsx';
import { useNavigate } from 'react-router-dom';
import { bulkImportEmployees, downloadEmployeeTemplate } from '@/factorial/api/employees';
import type { BulkImportResult } from '@/factorial/api/types';
import { normalizeImportRows } from '@/factorial/lib/employeeImport';
import { getErrorDetail } from '@/utils';

export default function EmployeesImportPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState<BulkImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const downloadTemplate = async () => {
    setErr('');
    try {
      await downloadEmployeeTemplate();
    } catch (e) {
      setErr(getErrorDetail(e, 'Не удалось скачать шаблон.'));
    }
  };

  const onFile = async (file: File) => {
    setBusy(true); setResult(null); setErr('');
    let rows: Record<string, string>[];
    try {
      const wb = XLSX.read(await file.arrayBuffer());
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
      rows = normalizeImportRows(raw);
    } catch {
      setErr('Не удалось прочитать файл. Нужен xlsx из шаблона.');
      setBusy(false);
      return;
    }
    if (!rows.length) {
      setErr('В файле нет строк с Email. Проверьте, что заголовки совпадают с шаблоном.');
      setBusy(false);
      return;
    }
    try {
      setResult(await bulkImportEmployees(rows));
    } catch (e) {
      setErr(getErrorDetail(e, 'Сервер не принял файл. Проверьте колонки и попробуйте ещё раз.'));
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

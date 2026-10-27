import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { updateEmployee, listEmployees } from '../api/employees';
import { formatPhone } from '../lib/phone';
import type { Employee } from '../api/types';

type Row = { last_name: string; first_name: string; position: string; department_start_date: string; phone: string };

// Массовое редактирование выбранных сотрудников (грид). Каждая строка сохраняется через
// updateEmployee (общая запись Employee — то же, что «Управление»). extra_data мёржится.
export default function BulkEditEmployeesModal({
  employees,
  onClose,
  onSaved,
}: {
  employees: Employee[];
  onClose: () => void;
  onSaved?: () => void;
}) {
  const qc = useQueryClient();
  const { data: allEmps = [] } = useQuery({ queryKey: ['fx', 'employees', 'table'], queryFn: () => listEmployees(true), retry: false });
  const positions = Array.from(new Set(allEmps.map((e) => (e.position || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'ru'));

  const buildInit = (): Record<number, Row> => {
    const m: Record<number, Row> = {};
    employees.forEach((e) => {
      const ex = (e.extra_data || {}) as Record<string, unknown>;
      const s = (v: unknown) => (v == null ? '' : String(v));
      m[e.id] = {
        last_name: s(ex.last_name),
        first_name: s(ex.first_name),
        position: s(e.position),
        department_start_date: e.department_start_date ? String(e.department_start_date).slice(0, 10) : '',
        phone: formatPhone(s(e.phone)),
      };
    });
    return m;
  };
  const [edits, setEdits] = useState<Record<number, Row>>(buildInit);
  const [err, setErr] = useState('');
  const setCell = (id: number, field: keyof Row, val: string) =>
    setEdits((s) => ({ ...s, [id]: { ...s[id], [field]: val } }));

  const save = useMutation({
    mutationFn: async () => {
      for (const e of employees) {
        const ed = edits[e.id];
        const baseExtra = (e.extra_data || {}) as Record<string, unknown>;
        const u = (v: string) => (v.trim() ? v.trim() : undefined);
        const extra = { ...baseExtra, last_name: u(ed.last_name), first_name: u(ed.first_name) };
        await updateEmployee(e.id, {
          position: ed.position.trim() || null,
          phone: ed.phone.trim() || null,
          department_start_date: ed.department_start_date ? `${ed.department_start_date}T00:00:00` : null,
          extra_data: extra,
        });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fx'] });
      onSaved?.();
      onClose();
    },
    onError: () => setErr('Не удалось сохранить часть строк. Проверьте данные и попробуйте ещё раз.'),
  });

  const textCell = (id: number, field: keyof Row, type = 'text') => (
    <input
      type={type}
      className="fx-input"
      style={{ padding: '6px 8px', minWidth: type === 'date' ? 140 : 120 }}
      value={edits[id][field]}
      onChange={(ev) => setCell(id, field, ev.target.value)}
    />
  );

  return createPortal(
    <div className="factorial-root" style={{ height: 'auto', background: 'transparent' }}>
    <div className="fx-modal-overlay" onClick={onClose}>
      <div
        className="fx-modal"
        style={{ width: 'min(980px, 96vw)', maxHeight: '90vh', overflow: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Массовое редактирование ({employees.length})</h3>
        <p className="fx-sub" style={{ marginBottom: 10 }}>
          Отдел меняется отдельно — кнопкой «Переместить» (write-through в «Управление»).
        </p>
        <div style={{ overflowX: 'auto' }}>
          <table className="w-full text-fx-sm" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr className="text-text-muted">
                <th className="text-left px-2 py-2">Сотрудник</th>
                <th className="text-left px-2 py-2">Фамилия</th>
                <th className="text-left px-2 py-2">Имя</th>
                <th className="text-left px-2 py-2">Должность</th>
                <th className="text-left px-2 py-2">Дата начала работы</th>
                <th className="text-left px-2 py-2">Телефон</th>
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => (
                <tr key={e.id} className="border-t border-card-border-soft">
                  <td className="px-2 py-1.5 whitespace-nowrap font-medium">{e.user_name || '—'}</td>
                  <td className="px-1 py-1">{textCell(e.id, 'last_name')}</td>
                  <td className="px-1 py-1">{textCell(e.id, 'first_name')}</td>
                  <td className="px-1 py-1">
                    <select
                      className="fx-select"
                      style={{ padding: '6px 8px', minWidth: 150 }}
                      value={edits[e.id].position}
                      onChange={(ev) => setCell(e.id, 'position', ev.target.value)}
                    >
                      <option value="">— Не выбрана —</option>
                      {positions.map((p) => (<option key={p} value={p}>{p}</option>))}
                      {edits[e.id].position && !positions.includes(edits[e.id].position) && (
                        <option value={edits[e.id].position}>{edits[e.id].position}</option>
                      )}
                    </select>
                  </td>
                  <td className="px-1 py-1">{textCell(e.id, 'department_start_date', 'date')}</td>
                  <td className="px-1 py-1">
                    <input
                      className="fx-input"
                      style={{ padding: '6px 8px', minWidth: 150 }}
                      value={edits[e.id].phone}
                      onChange={(ev) => setCell(e.id, 'phone', formatPhone(ev.target.value))}
                      placeholder="+7 (___) ___-__-__"
                      inputMode="tel"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
        <div className="fx-modal-actions">
          <button type="button" className="fx-btn fx-btn--secondary" onClick={onClose}>Отмена</button>
          <button type="button" className="fx-btn fx-btn--primary" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? 'Сохранение…' : 'Сохранить все'}
          </button>
        </div>
      </div>
    </div>
    </div>,
    document.body,
  );
}

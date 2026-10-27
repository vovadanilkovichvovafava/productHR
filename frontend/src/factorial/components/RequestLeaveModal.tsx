import { useState, FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createLeaveRequest } from '../api/employees';
import DatePickerFactorial from './DatePickerFactorial';
import { backdropClose } from '@/utils/backdropClose';
import { getErrorDetail } from '@/utils';

export default function RequestLeaveModal({ employeeId, onClose }: { employeeId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [type, setType] = useState('vacation');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const [err, setErr] = useState('');

  const days = start && end
    ? Math.max(1, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 86400000) + 1)
    : 0;

  const m = useMutation({
    mutationFn: () =>
      createLeaveRequest(employeeId, {
        type,
        start_date: `${start}T00:00:00`,
        end_date: `${end}T00:00:00`,
        days,
        reason: reason || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fx'] });
      onClose();
    },
    // Сервер говорит, что не так (даты, уволен, лимит) — показываем его текст.
    onError: (error) => setErr(getErrorDetail(error, 'Не удалось отправить запрос. Попробуйте ещё раз.')),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErr('');
    if (!start || !end || new Date(end) < new Date(start)) {
      setErr('Укажите корректные даты (конец не раньше начала).');
      return;
    }
    m.mutate();
  };

  return (
    <div className="fx-modal-overlay" {...backdropClose(onClose)}>
      <form className="fx-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>Запросить отпуск</h3>
        <div className="fx-field">
          <label>Тип</label>
          <select className="fx-select" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="vacation">Отпуск</option>
            <option value="sick">Больничный</option>
            <option value="family_leave">Семейные обстоятельства</option>
            <option value="bereavement">Отпуск по утрате</option>
          </select>
        </div>
        <div className="fx-field" style={{ display: 'flex', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label>С</label>
            {/* Больничный оформляют и задним числом — прошедшие даты для него открыты. */}
            <DatePickerFactorial value={start} onChange={setStart} disablePast={type !== 'sick'} />
          </div>
          <div style={{ flex: 1 }}>
            <label>По</label>
            <DatePickerFactorial value={end} onChange={setEnd} disablePast={type !== 'sick'} />
          </div>
        </div>
        <div className="fx-field">
          <label>Комментарий (необязательно)</label>
          <textarea className="fx-textarea" value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        {days > 0 && <div className="fx-sub">Дней: {days}</div>}
        {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
        <div className="fx-modal-actions">
          <button type="button" className="fx-btn fx-btn--secondary" onClick={onClose}>Отмена</button>
          <button type="submit" className="fx-btn fx-btn--primary" disabled={m.isPending}>
            {m.isPending ? 'Отправка…' : 'Отправить'}
          </button>
        </div>
      </form>
    </div>
  );
}

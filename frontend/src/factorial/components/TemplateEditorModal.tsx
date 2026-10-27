import { useState, FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createTemplate, updateTemplate } from '../api/documents';
import type { DocTemplate } from '../api/types';

const DEFAULT_CONTENT =
  'Настоящим {{name}}, должность {{position}}, отдел {{department}},\nподтверждает обязательство о неразглашении конфиденциальной информации.\n\nДата: {{date}}';

export default function TemplateEditorModal({ template, onClose }: { template: DocTemplate | null; onClose: () => void }) {
  const qc = useQueryClient();
  const isEdit = !!template;
  const [name, setName] = useState(template?.name || '');
  const [content, setContent] = useState(template?.content || DEFAULT_CONTENT);
  const [err, setErr] = useState('');

  const vars = Array.from(new Set((content.match(/\{\{(\w+)\}\}/g) || [])));

  const m = useMutation({
    mutationFn: () => (isEdit ? updateTemplate(template!.id, { name, content }) : createTemplate({ name, content })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['fx', 'templates'] }); onClose(); },
    onError: () => setErr('Не удалось сохранить шаблон.'),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErr('');
    if (!name.trim() || !content.trim()) { setErr('Заполните название и содержимое.'); return; }
    m.mutate();
  };

  return (
    <div className="fx-modal-overlay" onClick={onClose}>
      <form className="fx-modal" style={{ width: 560 }} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h3>{isEdit ? 'Редактировать шаблон' : 'Создать шаблон'}</h3>
        <div className="fx-field">
          <label>Название</label>
          <input className="fx-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="NDA — Соглашение о неразглашении" />
        </div>
        <div className="fx-field">
          <label>Содержимое (переменные: {'{{name}} {{position}} {{department}} {{date}} {{email}}'})</label>
          <textarea className="fx-textarea" style={{ minHeight: 170, fontFamily: 'monospace' }} value={content} onChange={(e) => setContent(e.target.value)} />
        </div>
        {vars.length > 0 && (
          <div className="fx-sub">Найдено переменных: {vars.map((v) => <span key={v} className="fx-pill" style={{ marginRight: 6 }}>{v}</span>)}</div>
        )}
        {err && <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 8 }}>{err}</div>}
        <div className="fx-modal-actions">
          <button type="button" className="fx-btn fx-btn--secondary" onClick={onClose}>Отмена</button>
          <button type="submit" className="fx-btn fx-btn--primary" disabled={m.isPending}>{m.isPending ? 'Сохранение…' : 'Сохранить'}</button>
        </div>
      </form>
    </div>
  );
}

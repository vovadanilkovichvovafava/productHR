import { useState } from 'react';
import { createPortal } from 'react-dom';

// «Уволен» / «Уволился» на доске «Штат» — только с причиной (Мария,
// 12.11.2026: «рекрутер при переводе на статус обязательно должен указать
// причину увольнения, без причины — не переведётся, она и будет видна на
// борде»). Причина уходит вместе со статусом и встаёт в колонку «Причина
// отказа». Вид — как у окна подтверждения (hf-confirm-modal).

export default function DepartureReasonModal({
  name,
  statusLabel,
  initial = '',
  onCancel,
  onSave,
}: {
  name: string;
  statusLabel: string;
  initial?: string;
  onCancel: () => void;
  /** Вернуть false — окно останется открытым с набранным текстом. */
  onSave: (reason: string) => Promise<boolean>;
}) {
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const ready = text.trim().length > 0;

  const save = async () => {
    if (!ready || busy) return;
    setBusy(true);
    try {
      const ok = await onSave(text.trim());
      if (!ok) setBusy(false);
    } catch {
      setBusy(false);
    }
  };

  return createPortal(
    <div
      className="hf-confirm-modal-backdrop"
      style={{ zIndex: 60 }}
      onMouseDown={(e) => {
        // Только нажатие НА фоне: выделение текста с отпусканием за краем
        // окна не должно закрывать его вместе с набранным.
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && !busy) onCancel();
      }}
    >
      <div role="dialog" aria-modal="true" className="hf-confirm-modal" onClick={(e) => e.stopPropagation()}>
        <div>
          <h3 className="hf-confirm-modal-title">{statusLabel}: причина увольнения</h3>
          <p className="hf-confirm-modal-subtitle">
            {name}. Без причины статус не сменится — она будет видна на доске в колонке «Причина отказа».
          </p>
        </div>
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save();
          }}
          rows={3}
          maxLength={2000}
          placeholder="Например: не прошёл испытательный срок"
          className="hf-departure-reason-input"
        />
        <div className="hf-confirm-modal-actions">
          <button type="button" onClick={onCancel} disabled={busy} className="hf-confirm-modal-cancel">
            Отмена
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!ready || busy}
            title={ready ? undefined : 'Напишите причину увольнения'}
            className="hf-confirm-modal-submit hf-confirm-modal-submit-warning whitespace-nowrap"
          >
            {busy ? 'Подождите…' : 'Сменить статус'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

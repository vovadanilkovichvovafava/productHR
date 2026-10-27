import { createPortal } from 'react-dom';
import clsx from 'clsx';
import type { Vacancy } from '@/types';
import { vacancyExitCopy } from '@/utils/vacancyExitCopy';

// Подтверждение «Выйти / Закрыть / Удалить» вакансию — одно окно на «Мои
// вакансии» и форму вакансии (20.10.2026). Раньше форма спрашивала окном
// браузера (window.confirm) со своей, третьей копией текстов, и в ней админ,
// сам не участвующий в вакансии, читал «Вы последний участник — она закроется
// полностью», хотя в ней работали другие. Вопросы — vacancyExitCopy.

export type VacancyConfirmAction = 'leave' | 'close' | 'delete';

export default function VacancyConfirmModal({
  action,
  vacancy,
  userId,
  busy,
  onCancel,
  onConfirm,
}: {
  action: VacancyConfirmAction;
  vacancy: Vacancy;
  userId: number | undefined | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const copy = action === 'delete' ? null : vacancyExitCopy(action, vacancy, userId, 'vacancy');
  return createPortal(
    <div
      className="hf-confirm-modal-backdrop"
      // Над окном формы вакансии (у обоих z-index 50).
      style={{ zIndex: 60 }}
      onClick={(e) => {
        e.stopPropagation();
        if (!busy) onCancel();
      }}
    >
      <div
        className={clsx('hf-confirm-modal', action === 'delete' && 'hf-confirm-modal-delete')}
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          <h3 className="hf-confirm-modal-title">{copy?.title ?? 'Удалить вакансию?'}</h3>
          <p className="hf-confirm-modal-subtitle">«{vacancy.title?.trim() || 'Без названия'}»</p>
          {copy?.text && <p className="hf-confirm-modal-subtitle">{copy.text}</p>}
          {action === 'delete' && (
            <p className="hf-confirm-modal-danger-text">
              Действие нельзя отменить. Кандидаты в воронке потеряют связь с этой вакансией.
            </p>
          )}
        </div>
        <div className="hf-confirm-modal-actions">
          <button type="button" onClick={onCancel} disabled={busy} className="hf-confirm-modal-cancel">
            Отмена
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={clsx(
              'hf-confirm-modal-submit',
              action === 'delete' ? 'hf-confirm-modal-submit-danger' : 'hf-confirm-modal-submit-warning',
            )}
          >
            {busy ? 'Применяем…' : copy?.confirmLabel ?? 'Удалить'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

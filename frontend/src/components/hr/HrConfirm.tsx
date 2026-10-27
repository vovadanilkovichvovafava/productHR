import { createPortal } from 'react-dom';
import clsx from 'clsx';

// Окно подтверждения в стиле сайта вместо window.confirm (20.10.2026): в
// «Анкетах» удаление шаблона и ответов спрашивалось окном браузера — серым,
// с адресом сайта в заголовке, его легко «прощёлкать». Вид — тот же, что у
// окна выхода из вакансии (hf-confirm-modal).

export default function HrConfirm({
  title,
  subtitle,
  danger,
  confirmLabel,
  secondary,
  busy = false,
  inDialog = false,
  onCancel,
  onConfirm,
}: {
  title: string;
  subtitle?: string;
  /** Красная строка «что будет потеряно». */
  danger?: string;
  confirmLabel: string;
  /** Третья кнопка, например «Выйти без сохранения». */
  secondary?: { label: string; onClick: () => void };
  busy?: boolean;
  /** Окно открыто поверх выдвижной панели (Radix Dialog): рисуем внутри неё,
   *  а не в body — иначе оно под панелью, а клик по нему закрывает панель. */
  inDialog?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const node = (
    <div
      className="hf-confirm-modal-backdrop"
      style={{ zIndex: inDialog ? 1100 : 60 }}
      onClick={(e) => {
        e.stopPropagation();
        if (!busy) onCancel();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && !busy) onCancel();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        className={clsx('hf-confirm-modal', danger && 'hf-confirm-modal-delete')}
        // Три кнопки в стандартные 384 px не влезают — переносились по словам.
        style={secondary ? { width: 'min(100%, 480px)' } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          <h3 className="hf-confirm-modal-title">{title}</h3>
          {subtitle && <p className="hf-confirm-modal-subtitle">{subtitle}</p>}
          {danger && <p className="hf-confirm-modal-danger-text">{danger}</p>}
        </div>
        <div className="hf-confirm-modal-actions">
          <button type="button" onClick={onCancel} disabled={busy} className="hf-confirm-modal-cancel">
            Отмена
          </button>
          {secondary && (
            <button type="button" onClick={secondary.onClick} disabled={busy} className="hf-confirm-modal-cancel whitespace-nowrap">
              {secondary.label}
            </button>
          )}
          <button
            type="button"
            autoFocus
            onClick={onConfirm}
            disabled={busy}
            className={clsx(
              'hf-confirm-modal-submit',
              danger ? 'hf-confirm-modal-submit-danger' : 'hf-confirm-modal-submit-warning',
              'whitespace-nowrap',
            )}
          >
            {busy ? 'Подождите…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
  return inDialog ? node : createPortal(node, document.body);
}

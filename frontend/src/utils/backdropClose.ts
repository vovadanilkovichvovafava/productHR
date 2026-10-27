import type { MouseEvent as ReactMouseEvent } from 'react';

/**
 * Пропсы для ФОНА модалки: закрытие по клику мимо окна — без ложных
 * срабатываний на выделении текста.
 *
 * Наивный `onClick={onClose}` на фоне ломается о то, как браузер доставляет
 * `click`: событие приходит не туда, где отпустили кнопку, а на ОБЩЕГО ПРЕДКА
 * `mousedown` и `mouseup`. Стоит выделить текст в поле внутри окна и отпустить
 * кнопку чуть за его краем — общим предком оказывается фон, он получает `click`
 * и закрывает окно вместе со всем несохранённым. Проверка
 * `e.target === e.currentTarget` сама по себе не спасает: у такого клика target
 * и есть фон.
 *
 * Найдено на модалке парсинга резюме: рекрутёр выделял текст в «Комментарии»,
 * и окно захлопывалось «само», теряя распознанное резюме (Эльвира, 2026-09-08).
 *
 * Закрываем, только если жест и НАЧАЛСЯ, и закончился на самом фоне. Состояние
 * жеста держим в data-атрибуте самого элемента, а не в ref — чтобы это была
 * обычная функция, а не хук: её можно звать прямо в JSX, в том числе во
 * вложенных модалках внутри одного файла.
 *
 * ```tsx
 * <div className="fixed inset-0 ..." {...backdropClose(onClose)}>
 *   <div onClick={(e) => e.stopPropagation()}>…</div>
 * </div>
 * ```
 */
export function backdropClose(onClose: () => void) {
  return {
    onMouseDown: (e: ReactMouseEvent) => {
      (e.currentTarget as HTMLElement).dataset.backdropArmed = String(
        e.target === e.currentTarget,
      );
    },
    onClick: (e: ReactMouseEvent) => {
      const el = e.currentTarget as HTMLElement;
      const armed = el.dataset.backdropArmed === 'true';
      delete el.dataset.backdropArmed;
      if (e.target !== e.currentTarget || !armed) return;
      onClose();
    },
  };
}

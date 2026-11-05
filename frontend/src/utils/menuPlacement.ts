import { useLayoutEffect, useRef, useState } from 'react';
import type { DependencyList, RefObject } from 'react';

/**
 * Куда открыть всплывающий список у кнопки: вниз, а если внизу не помещается
 * и сверху места больше — вверх. Высота урезается до свободного места, список
 * в нём прокручивается.
 *
 * Мария, 05.11.2026 («Штат», «+» у HR в нижней строке): «открывается поле внизу
 * страницы, и оно не видно, нет возможности выбора». Меню в «Штате», в форме
 * вакансии и @-упоминания в комментарии считали место только ПОД кнопкой —
 * у нижнего края окна список уходил за экран целиком.
 */
export interface MenuPlacement {
  top: number;
  /** Только когда список не влез целиком: столько места есть на самом деле. */
  maxHeight?: number;
}

export function placeMenu(
  anchor: { top: number; bottom: number },
  menuHeight: number,
  viewportHeight: number = window.innerHeight,
  gap = 4,
  margin = 8,
): MenuPlacement {
  const below = viewportHeight - anchor.bottom - gap - margin;
  const above = anchor.top - gap - margin;
  if (menuHeight <= below || below >= above) {
    return {
      top: anchor.bottom + gap,
      ...(menuHeight > below ? { maxHeight: Math.max(below, 0) } : {}),
    };
  }
  const height = Math.min(menuHeight, above);
  return {
    top: anchor.top - gap - height,
    ...(menuHeight > above ? { maxHeight: above } : {}),
  };
}

/**
 * Для меню, которое рисуется под кнопкой (`position: fixed`): после отрисовки
 * меряет его и отдаёт новое место, если внизу оно не влезает. До первого
 * замера — null, компонент ставит меню, как ставил. Пересчёт идёт в
 * useLayoutEffect, поэтому меню не мигает внизу перед переносом наверх.
 * `deps` — то, от чего меняется высота или место (пункты, позиция курсора).
 */
export function useMenuPlacement(
  open: boolean,
  getAnchor: () => { top: number; bottom: number } | null | undefined,
  menuRef: RefObject<HTMLElement | null>,
  deps: DependencyList = [],
  gap = 4,
): MenuPlacement | null {
  const [placement, setPlacement] = useState<MenuPlacement | null>(null);
  // Предел высоты из CSS читаем один раз за открытие: потом в стиле уже наш.
  const capRef = useRef<number | null>(null);

  useLayoutEffect(() => {
    const menu = menuRef.current;
    if (!open || !menu) {
      capRef.current = null;
      setPlacement(null);
      return;
    }
    if (capRef.current === null) {
      const css = parseFloat(getComputedStyle(menu).maxHeight); // 'none' → NaN
      capRef.current = Number.isFinite(css) ? css : Infinity;
    }
    const anchor = getAnchor();
    if (!anchor) return;
    const natural = Math.min(menu.scrollHeight + menu.offsetHeight - menu.clientHeight, capRef.current);
    const next = placeMenu(anchor, natural, window.innerHeight, gap);
    setPlacement((prev) =>
      prev && prev.top === next.top && prev.maxHeight === next.maxHeight ? prev : next,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ...deps]);

  return placement;
}

/** Стиль меню: наше место поверх исходного; урезанное — с прокруткой. */
export function placementStyle(
  placement: MenuPlacement | null,
): { top?: number; maxHeight?: number; overflowY?: 'auto' } {
  if (!placement) return {};
  return placement.maxHeight === undefined
    ? { top: placement.top }
    : { top: placement.top, maxHeight: placement.maxHeight, overflowY: 'auto' };
}

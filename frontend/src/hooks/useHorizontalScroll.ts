import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefCallback,
} from "react";

export interface UseHorizontalScrollOptions {
  /**
   * Сколько пикселей прокручивать за одно нажатие стрелки.
   * По умолчанию ~85% ширины видимой области (комфортно для таб-баров).
   */
  step?: number;
  /** Поведение программной прокрутки по клику. По умолчанию "smooth". */
  behavior?: ScrollBehavior;
}

export interface UseHorizontalScrollReturn<T extends HTMLElement = HTMLDivElement> {
  /**
   * Callback-ref: повесить на контейнер со скроллом (overflow-x: auto).
   * Именно callback-ref (а не useRef) — чтобы наблюдатели навешивались ровно
   * тогда, когда контейнер появляется в DOM, и снимались при удалении. Это
   * переживает условный рендер (`cond && <div ref={ref} />`).
   */
  ref: RefCallback<T>;
  /** Контент шире контейнера — есть что скроллить. */
  isOverflowing: boolean;
  /** Скролл не в самом начале (можно влево). */
  canScrollLeft: boolean;
  /** Скролл не в самом конце (можно вправо). */
  canScrollRight: boolean;
  /** Прокрутить на шаг влево. */
  scrollLeft: () => void;
  /** Прокрутить на шаг вправо. */
  scrollRight: () => void;
  /** Прокрутить в указанную сторону. */
  scrollByDirection: (direction: "left" | "right") => void;
  /** Принудительно пересчитать стрелки (обычно не нужно — есть авто-наблюдатели). */
  recalculate: () => void;
}

// Субпиксельный люфт: scrollWidth/clientWidth/scrollLeft бывают дробными, и из-за
// округления правая стрелка могла «застревать» в ~0.5px от конца.
const EPSILON = 1;

const DEFAULT_STATE = {
  isOverflowing: false,
  canScrollLeft: false,
  canScrollRight: false,
};

/**
 * Горизонтальный скролл для таб-баров / лент-полосок.
 *
 * Контейнер скроллится нативно (трекпад, Shift + колесо мыши). Хук считает,
 * нужно ли показывать стрелки «влево»/«вправо», и даёт smooth-прокрутку по клику.
 *
 * Состояние пересчитывается на:
 *  • скролл контейнера;
 *  • ресайз контейнера и его детей (ResizeObserver);
 *  • добавление/удаление/изменение табов (MutationObserver);
 *  • ресайз окна.
 * Все пересчёты схлопнуты в один кадр через requestAnimationFrame. Это и убирает
 * «неконсистентность»: стрелки корректны не только при скролле, но и когда
 * меняются размеры/набор табов.
 *
 * Скроллбар прячется средствами CSS (.hf-hscroll__viewport). Рассчитан на LTR.
 */
export function useHorizontalScroll<T extends HTMLElement = HTMLDivElement>(
  options: UseHorizontalScrollOptions = {},
): UseHorizontalScrollReturn<T> {
  const { step, behavior = "smooth" } = options;
  const elementRef = useRef<T | null>(null);
  const [state, setState] = useState(DEFAULT_STATE);

  const recalculate = useCallback(() => {
    const el = elementRef.current;
    if (!el) return;
    const maxScrollLeft = el.scrollWidth - el.clientWidth;
    const isOverflowing = maxScrollLeft > EPSILON;
    const next = {
      isOverflowing,
      canScrollLeft: isOverflowing && el.scrollLeft > EPSILON,
      canScrollRight: isOverflowing && el.scrollLeft < maxScrollLeft - EPSILON,
    };
    // Не дёргаем ререндер, если ничего не поменялось (Observer-ы стреляют пачками).
    setState((prev) =>
      prev.isOverflowing === next.isOverflowing &&
      prev.canScrollLeft === next.canScrollLeft &&
      prev.canScrollRight === next.canScrollRight
        ? prev
        : next,
    );
  }, []);

  // rAF-коалесинг: ResizeObserver/MutationObserver/scroll стреляют пачками —
  // читаем layout не чаще одного раза за кадр.
  const rafId = useRef(0);
  const scheduleRecalculate = useCallback(() => {
    if (rafId.current) return;
    rafId.current = requestAnimationFrame(() => {
      rafId.current = 0;
      recalculate();
    });
  }, [recalculate]);

  // Отписка от текущего узла — между сменами элемента и при размонтировании.
  const detach = useRef<(() => void) | null>(null);

  const ref = useCallback<RefCallback<T>>(
    (node) => {
      detach.current?.();
      detach.current = null;
      elementRef.current = node;
      if (!node) {
        setState(DEFAULT_STATE);
        return;
      }

      node.addEventListener("scroll", scheduleRecalculate, { passive: true });
      window.addEventListener("resize", scheduleRecalculate);

      // ResizeObserver — и размеры контейнера, и суммарная ширина контента (дети).
      const ro =
        typeof ResizeObserver !== "undefined"
          ? new ResizeObserver(scheduleRecalculate)
          : null;
      const observeAll = () => {
        if (!ro) return;
        ro.disconnect();
        ro.observe(node);
        for (const child of Array.from(node.children)) ro.observe(child);
      };
      observeAll();

      // MutationObserver — добавили/убрали таб или сменился текст лейбла.
      const mo =
        typeof MutationObserver !== "undefined"
          ? new MutationObserver(() => {
              observeAll();
              scheduleRecalculate();
            })
          : null;
      mo?.observe(node, { childList: true, subtree: true, characterData: true });

      scheduleRecalculate();

      detach.current = () => {
        node.removeEventListener("scroll", scheduleRecalculate);
        window.removeEventListener("resize", scheduleRecalculate);
        ro?.disconnect();
        mo?.disconnect();
      };
    },
    [scheduleRecalculate],
  );

  // Подчистить наблюдатели и rAF при размонтировании компонента-потребителя.
  useEffect(
    () => () => {
      detach.current?.();
      detach.current = null;
      if (rafId.current) {
        cancelAnimationFrame(rafId.current);
        rafId.current = 0;
      }
    },
    [],
  );

  const scrollByDirection = useCallback(
    (direction: "left" | "right") => {
      const el = elementRef.current;
      if (!el) return;
      const amount = step ?? Math.max(Math.round(el.clientWidth * 0.85), 120);
      el.scrollBy({ left: direction === "left" ? -amount : amount, behavior });
    },
    [step, behavior],
  );

  const scrollLeft = useCallback(
    () => scrollByDirection("left"),
    [scrollByDirection],
  );
  const scrollRight = useCallback(
    () => scrollByDirection("right"),
    [scrollByDirection],
  );

  return {
    ref,
    isOverflowing: state.isOverflowing,
    canScrollLeft: state.canScrollLeft,
    canScrollRight: state.canScrollRight,
    scrollLeft,
    scrollRight,
    scrollByDirection,
    recalculate,
  };
}

export default useHorizontalScroll;

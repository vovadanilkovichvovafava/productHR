import { type ReactNode } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import clsx from "clsx";
import {
  useHorizontalScroll,
  type UseHorizontalScrollOptions,
} from "../../hooks/useHorizontalScroll";

export interface HorizontalScrollerProps extends UseHorizontalScrollOptions {
  /** Содержимое ленты — табы, чипы, кнопки этапов и т.п. */
  children: ReactNode;
  /** Класс корневого контейнера. */
  className?: string;
  /**
   * Класс области скролла. Сюда удобно класть gap/padding контента,
   * например "gap-2 py-1" или "px-2" (чтобы крайние табы не прятались под стрелку).
   */
  viewportClassName?: string;
  /** aria-label левой стрелки. */
  leftLabel?: string;
  /** aria-label правой стрелки. */
  rightLabel?: string;
}

/**
 * Обёртка для горизонтальной ленты табов: нативный скролл (трекпад / Shift+колесо)
 * + умные стрелки (появляются только при переполнении; левая прячется в начале,
 * правая — в конце), плавная прокрутка по клику, скрытый скроллбар.
 *
 * Drop-in: оборачиваешь существующий ряд табов, верстку внутри менять не нужно.
 *
 * @example
 * <HorizontalScroller viewportClassName="gap-2 py-1">
 *   {stages.map((s) => (
 *     <button key={s.key} className="...">{s.label}</button>
 *   ))}
 * </HorizontalScroller>
 */
export default function HorizontalScroller({
  children,
  className,
  viewportClassName,
  step,
  behavior,
  leftLabel = "Прокрутить влево",
  rightLabel = "Прокрутить вправо",
}: HorizontalScrollerProps) {
  const { ref, canScrollLeft, canScrollRight, scrollLeft, scrollRight } =
    useHorizontalScroll<HTMLDivElement>({ step, behavior });

  return (
    <div className={clsx("hf-hscroll", className)}>
      {canScrollLeft && (
        <button
          type="button"
          aria-label={leftLabel}
          className="hf-hscroll__arrow hf-hscroll__arrow--left"
          onClick={scrollLeft}
        >
          <ChevronLeft className="hf-hscroll__arrow-icon" aria-hidden="true" />
        </button>
      )}

      <div ref={ref} className={clsx("hf-hscroll__viewport", viewportClassName)}>
        {children}
      </div>

      {canScrollRight && (
        <button
          type="button"
          aria-label={rightLabel}
          className="hf-hscroll__arrow hf-hscroll__arrow--right"
          onClick={scrollRight}
        >
          <ChevronRight className="hf-hscroll__arrow-icon" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

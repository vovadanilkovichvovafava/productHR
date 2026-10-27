import clsx from "clsx";
import { X } from "lucide-react";

// ---- Яркие ярлыки у имени кандидата ----
// С 21.09.2026 — свой справочник тегов, отдельный от меток (метки = сорсеры).
// Форма данных — {name, color}, где color это CSS-значение из палитры
// ('var(--hf-status-purple)').
//
// Поле text и ключи палитры ('pink'/'purple'/…) — наследство от старого
// хранения в extra_data.headline_tags. Держим их читаемыми: бэкафилл ничего из
// extra_data не удаляет, и на карточках, куда свежие данные ещё не доехали,
// чип должен рисоваться, а не падать.
export type HeadlineTag = {
  name?: string;
  /** Старое поле. Используется, если name не задан. */
  text?: string;
  color: string;
};

export const HEADLINE_TAG_COLORS: Record<
  string,
  { bg: string; text: string; border: string }
> = {
  pink: { bg: "#fbdced", text: "#be185d", border: "#f6b8d6" },
  purple: { bg: "#ede9fe", text: "#6d28d9", border: "#ddd6fe" },
  blue: { bg: "#dbeafe", text: "#1d4ed8", border: "#bfdbfe" },
  teal: { bg: "#ccfbf1", text: "#0f766e", border: "#99f6e4" },
  green: { bg: "#dcfce7", text: "#15803d", border: "#bbf7d0" },
  amber: { bg: "#fef3c7", text: "#b45309", border: "#fde68a" },
  red: { bg: "#fee2e2", text: "#b91c1c", border: "#fecaca" },
};
export const HEADLINE_TAG_COLOR_KEYS = Object.keys(HEADLINE_TAG_COLORS);

/** Достаёт валидные теги из extra_data (или из готового массива). */
export function readHeadlineTags(source: unknown): HeadlineTag[] {
  let raw: unknown = source;
  if (source && !Array.isArray(source)) {
    raw = (source as { headline_tags?: unknown }).headline_tags;
  }
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (t): t is HeadlineTag =>
        !!t &&
        (typeof (t as HeadlineTag).text === "string" ||
          typeof (t as HeadlineTag).name === "string"),
    )
    .map((t) => ({ name: t.name, text: t.text, color: t.color || "pink" }));
}

export function HeadlineTagChip({
  tag,
  small,
  onRemove,
}: {
  tag: HeadlineTag;
  small?: boolean;
  onRemove?: () => void;
}) {
  // Ключ старой палитры — рисуем как раньше, чтобы недоехавшие карточки не
  // меняли вид. Всё остальное считаем цветом справочника.
  const legacy = HEADLINE_TAG_COLORS[tag.color];
  const style = legacy
    ? { background: legacy.bg, color: legacy.text, border: `1px solid ${legacy.border}` }
    : {
        background: `color-mix(in srgb, ${tag.color} 18%, transparent)`,
        color: tag.color,
        border: `1px solid color-mix(in srgb, ${tag.color} 35%, transparent)`,
      };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full font-semibold whitespace-nowrap",
        small ? "px-2 py-[1px] text-[11px]" : "px-2.5 py-[3px] text-[12px]",
      )}
      style={style}
    >
      {tag.name || tag.text}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          title="Убрать тег"
          className="ml-0.5 inline-flex items-center opacity-60 hover:opacity-100"
          style={{ color: style.color }}
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </span>
  );
}

import clsx from "clsx";
import { parseServerDate } from "@/utils/date";

// Мелкие части ленты карточки (значки, формат даты, текст для копирования,
// эмодзи реакций) — общие для CandidateVacancyCard и строки ленты
// (вынесено из CandidateVacancyCard, 20.10.2026).

// Набор эмодзи для пикера реакций.
export const REACTION_EMOJIS = ["👍", "❤️", "🔥", "🎉", "👀", "✅", "😂", "🙏"];

export function TimelineUserGlyph({
  surface = "stage",
  align = "stage",
}: {
  surface?: "stage" | "white";
  align?: "stage" | "notes";
}) {
  return (
    <span
      aria-hidden="true"
      className={clsx(
        "hf-timeline-user-glyph",
        align === "stage"
          ? "hf-timeline-user-glyph-stage"
          : "hf-timeline-user-glyph-notes",
        surface === "white"
          ? "hf-timeline-user-glyph-white-surface"
          : "hf-timeline-user-glyph-stage-surface",
      )}
    >
      <span className="hf-timeline-user-head" />
      <span className="hf-timeline-user-body" />
    </span>
  );
}

export function TimelineDot({ align = "stage" }: { align?: "stage" | "notes" }) {
  return (
    <span
      aria-hidden="true"
      className={clsx(
        "hf-timeline-dot",
        align === "stage" ? "hf-timeline-dot-stage" : "hf-timeline-dot-notes",
      )}
    />
  );
}

export function TimelineMetaIcon() {
  return (
    <span
      aria-hidden="true"
      className="hf-timeline-meta-icon"
    >
      <span className="hf-timeline-meta-eye-left" />
      <span className="hf-timeline-meta-eye-right" />
      <span className="hf-timeline-meta-mouth" />
    </span>
  );
}

// Пояс ТОГО, КТО СМОТРИТ: время в ленте и так местное (Date.getHours), а в
// подсказке к правке подписываем, в каком оно поясе — у рекрутёров разные
// (24.09.2026). Считается один раз на модуль: в рамках сессии не меняется.
export const localZoneLabel = (() => {
  const offsetMin = -new Date().getTimezoneOffset();
  const sign = offsetMin >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMin);
  const hours = Math.floor(abs / 60);
  const minutes = abs % 60;
  return `GMT${sign}${hours}${minutes ? `:${String(minutes).padStart(2, "0")}` : ""}`;
})();

export function formatTimelineDate(dateStr: string): string {
  const date = parseServerDate(dateStr);
  const months = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
  ];
  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${day} ${month} ${year}, ${hours}:${minutes}`;
}

// Текст записи таймлайна для копирования в буфер: тот же sanitizeHtml, что и
// рендер (event.title/body). НЕ innerText — на элементе, не прикреплённом к
// документу (нет layout), innerText игнорирует <br>/блочные теги и склеивает
// текст в одну строку. Поэтому переносы строк проставляем вручную ДО парсинга.
export function htmlToPlainText(html: string): string {
  const withBreaks = html
    .replace(/<br\s*\/?>/gi, "\n")
    // Перенос ПЕРЕД началом блока (список/абзац сразу после инлайн-текста без
    // <br> между ними иначе слипается с предыдущей строкой, напр. «Контакт:
    // t.me/ivan_petrov• Пункт А»). <li> не сюда — у него свой маркер ниже.
    .replace(/<(p|div|ul|ol|h[1-6])[^>]*>/gi, "\n")
    .replace(/<li[^>]*>/gi, "• ")
    .replace(/<\/(p|div|ul|ol|li|h[1-6])>/gi, "\n");
  const div = document.createElement("div");
  div.innerHTML = withBreaks;
  return (div.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

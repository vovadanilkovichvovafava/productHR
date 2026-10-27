// ================================================================
// ImportedParticipations — анкеты импортированных прохождений (ClickUp-архив).
//
// Один человек = несколько прохождений, каждое = связка «воронка + рекрутёр»
// со своей анкетой (cf:-ответы). Рисуем их сгруппированно во вкладке «Анкеты»:
// заголовок-метка «{воронка} · {рекрутёр}» + Q&A. ClickUp-вложения (в CSV это
// JSON-массив) показываем чистой кликабельной ссылкой, а не сырым JSON.
// ================================================================
import { Fragment, type ReactNode } from "react";
import { Paperclip } from "lucide-react";
import type { KanbanCard } from "@/services/api/candidates";

export type Participation = {
  vacancy_title?: string;
  recruiter?: string;
  status?: string;
  anketa?: Array<{ question?: string; answer?: string }>;
  date?: string;
  url?: string;
};

/** Прохождения кандидата из extra_data.participations (импорт ClickUp). */
export function readParticipations(card: KanbanCard): Participation[] {
  const ed = card.extra_data as Record<string, unknown> | undefined;
  return Array.isArray(ed?.participations)
    ? (ed!.participations as Participation[])
    : [];
}

const LINK_CLS =
  "text-[var(--hf-cyan-700)] underline break-all hf-dark-disabled:text-[var(--hf-cyan-400)]";

function linkify(text: string): ReactNode {
  return text.split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a key={i} href={part} target="_blank" rel="noreferrer" className={LINK_CLS}>
        {part}
      </a>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

// ClickUp-поле «вложение» в CSV = JSON-массив [{title,url,mimetype,...}].
// Показываем вложения кликабельными ссылками, а не сырым JSON-текстом.
// Экспортируется: тот же рендер нужен и в объединённой анкете (ResumeTab),
// иначе там ClickUp-вложение вываливается сырым JSON.
// ClickUp поле «прогресс/оценка» = {"current": N, "percent_completed": M}
// (напр. HR-рейтинги «Техническая экспертиза»). Разбираем, чтобы не показывать
// сырой JSON.
function parseProgress(answer: string): { current: number; percent: number } | null {
  const t = (answer || "").trim();
  if (!t.startsWith("{") || !t.includes("percent_completed")) return null;
  try {
    const o = JSON.parse(t) as Record<string, unknown>;
    if (o && typeof o === "object" && "percent_completed" in o) {
      return { current: Number(o.current) || 0, percent: Number(o.percent_completed) || 0 };
    }
  } catch {
    /* не JSON */
  }
  return null;
}

// Пустая оценка (0/0) — поле никто не заполнял; строку из анкеты скрываем.
export function isBlankAnswer(answer: string): boolean {
  const t = (answer || "").trim();
  if (!t) return true;
  const p = parseProgress(t);
  return !!p && p.current === 0 && p.percent === 0;
}

export function renderAnswer(answer: string): ReactNode {
  const t = (answer || "").trim();
  // Поле-оценка {current, percent_completed} → «M%», а не сырой JSON.
  const prog = parseProgress(t);
  if (prog) return `${prog.percent}%`;
  // ClickUp «Местонахождение» = geo-JSON {location, place_id, formatted_address} —
  // показываем читаемый адрес, а не сырой JSON.
  if (t.startsWith("{") && t.includes("formatted_address")) {
    try {
      const obj = JSON.parse(t) as Record<string, unknown>;
      if (typeof obj.formatted_address === "string" && obj.formatted_address.trim()) {
        return obj.formatted_address;
      }
    } catch {
      /* не JSON — покажем как текст ниже */
    }
  }
  // ClickUp «вложение» = JSON-массив [{title,url,mimetype,...}].
  if (
    t.startsWith("[") &&
    (t.includes("clickup-attachments") || t.includes('"mimetype"') || t.includes('"url"'))
  ) {
    try {
      const arr = JSON.parse(t);
      if (Array.isArray(arr) && arr.length > 0 && arr.every((a) => a && typeof a === "object")) {
        return (
          <div className="flex flex-col gap-[4px]">
            {arr.map((a: Record<string, unknown>, i) => {
              const url = typeof a.url === "string" ? a.url : "";
              const title =
                (typeof a.title === "string" && a.title) ||
                (typeof a.name === "string" && a.name) ||
                "вложение";
              return url ? (
                <a
                  key={i}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className={`inline-flex items-center gap-[6px] ${LINK_CLS}`}
                >
                  <Paperclip className="h-[13px] w-[13px] shrink-0" />
                  {title}
                </a>
              ) : (
                <Fragment key={i}>{title}</Fragment>
              );
            })}
          </div>
        );
      }
    } catch {
      /* не JSON — покажем как текст ниже */
    }
  }
  return linkify(answer);
}

export default function ImportedParticipations({
  participations,
}: {
  participations: Participation[];
}) {
  const list = (participations || []).filter(
    (p) => (p.anketa && p.anketa.length) || p.vacancy_title || p.recruiter,
  );
  if (list.length === 0) return null;
  return (
    <div className="p-5 max-w-3xl space-y-6">
      {list.map((p, i) => {
        const label = [p.vacancy_title, p.recruiter].filter(Boolean).join(" · ");
        const qa = (p.anketa || []).filter(
          (r) => (r.question || "").trim() && !isBlankAnswer(r.answer || ""),
        );
        return (
          <div key={i}>
            <div className="mb-2 space-y-0.5">
              <h3 className="text-sm font-semibold text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                {label || "Прохождение"}
              </h3>
              {p.status && (
                <div className="text-xs text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                  Статус: <span className="font-medium">{p.status}</span>
                </div>
              )}
            </div>
            {qa.length > 0 ? (
              <div className="rounded-lg border border-[color:var(--hf-main-200)] overflow-hidden hf-dark-disabled:border-[color:var(--hf-white-alpha-06)]">
                {qa.map((r, j) => (
                  <div
                    key={j}
                    className="grid grid-cols-1 gap-1 border-b border-[color:var(--hf-main-100)] px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(150px,240px)_1fr] sm:gap-4 hf-dark-disabled:border-[color:var(--hf-white-alpha-05)]"
                  >
                    <div className="text-xs font-medium text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                      {r.question}
                    </div>
                    <div className="whitespace-pre-wrap break-words text-sm text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                      {renderAnswer(r.answer || "")}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs italic text-[var(--hf-main-500)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                Анкета не заполнена
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

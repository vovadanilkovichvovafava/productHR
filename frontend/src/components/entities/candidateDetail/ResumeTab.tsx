// ================================================================
// ResumeTab — единый компонент просмотра резюме кандидата.
//
// Вынесен ВЕРБАТИМ из AllCandidatesPage, чтобы «Все кандидаты» и воронка
// (RecruiterFunnelsPage) использовали ОДИН И ТОТ ЖЕ просмотрщик резюме —
// один источник истины, идентичное поведение. Экспортирует также
// useResumeSources (хук для подсчёта вкладок «Резюме» родителем).
// ================================================================
import { useState, useEffect, memo } from "react";
import type { ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Eye,
  Printer,
  Download,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Type,
} from "lucide-react";
import clsx from "clsx";
import toast from "react-hot-toast";
import {
  getEntityFiles,
  downloadEntityFile,
  type EntityFile,
} from "@/services/api/entities";
import type { KanbanCard } from "@/services/api/candidates";
import {
  buildResumeSources,
  type ResumeSource,
  type ResumeDemoData,
} from "./model";
// Единый рендер ответа анкеты: ClickUp-вложение (JSON) → кликабельная ссылка,
// гео-JSON → адрес. Иначе объединённая анкета вываливает сырой JSON.
import { renderAnswer, isBlankAnswer } from "./ImportedParticipations";

// ---------- helpers (приватные копии — изоляция модуля) ----------

function getInitials(name: string): string {
  const p = name.trim().split(/\s+/);
  if (p.length >= 2) return (p[0][0] + p[1][0]).toUpperCase();
  return (p[0]?.[0] || "?").toUpperCase();
}

function formatDateFull(dateStr: string): string {
  return new Date(dateStr).toLocaleString("ru", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatResumeSaved(dateStr: string): string {
  const date = new Date(dateStr);
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
  return `${day} ${month} ${year} в ${hours}:${minutes}`;
}

function formatPhoneDisplay(phone?: string): string {
  if (!phone) return "";
  const digits = phone.replace(/\D/g, "");
  const match = digits.match(/^7(\d{3})(\d{3})(\d{4})$/);
  if (match) return `+7 ${match[1]} ${match[2]} ${match[3]}`;
  return phone;
}

function HfSkeletonBlock({ className }: { className: string }) {
  return <div className={clsx("hf-loading-skeleton", className)} />;
}

// ---------- Imported (ClickUp) questionnaire ----------

const IMPORT_QUESTIONNAIRE_EXTRA_LABELS: Record<string, string> = {
  location: "Местонахождение",
};

function normalizeImportedValue(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v.trim();
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v))
    return v.map((x) => normalizeImportedValue(x)).filter(Boolean).join(", ");
  return "";
}

type QaPair = { question: string; answer: string };

function parseFormSubmission(description: string): QaPair[] {
  if (!description) return [];
  const pairs: QaPair[] = [];
  let question: string | null = null;
  let answer: string[] = [];
  const flush = () => {
    if (question != null) {
      pairs.push({
        question: question.replace(/:+\s*$/, "").trim(),
        answer: answer.join("\n").trim(),
      });
    }
  };
  for (const rawLine of description.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.endsWith(":")) {
      flush();
      question = line;
      answer = [];
    } else if (question != null) {
      answer.push(rawLine);
    }
  }
  flush();
  return pairs.filter((p) => p.question);
}

type MergedFrom = {
  entity_id: number;
  name: string | null;
  merged_at: string;
  merged_by: number;
  merged_by_name: string | null;
  extra_data: Record<string, unknown>;
};

function getImportedQuestionnaire(card: KanbanCard): {
  rows: Array<{ label: string; value: string }>;
  clickupUrl: string | null;
} {
  const ed = card.extra_data as Record<string, unknown> | undefined;
  let rows: Array<{ label: string; value: string }> = [];
  let clickupUrl: string | null = null;
  if (ed) {
    clickupUrl = typeof ed.clickup_url === "string" ? ed.clickup_url : null;

    // 1) Структурированные пары, если бэк их когда-нибудь положит сам.
    const formQa = ed.form_qa;
    if (Array.isArray(formQa) && formQa.length > 0) {
      rows = formQa
        .map((p) => {
          const o = (p ?? {}) as Record<string, unknown>;
          return {
            label: normalizeImportedValue(o.question ?? o.q),
            value: normalizeImportedValue(o.answer ?? o.a),
          };
        })
        .filter((r) => r.label && r.value && !isBlankAnswer(r.value));
    }

    // 2) Иначе парсим текст формы из description — достоверные пары Q→A.
    if (rows.length === 0) {
      rows = parseFormSubmission(normalizeImportedValue(ed.description))
        .map((p) => ({ label: p.question, value: p.answer }))
        .filter((r) => r.label && r.value && !isBlankAnswer(r.value));
    }

    // 3) Фолбэк (списки без формы): сырые cf:* поля как есть.
    if (rows.length === 0) {
      for (const [k, raw] of Object.entries(ed)) {
        let label: string | null = null;
        if (k.startsWith("cf:")) label = k.slice(3).trim();
        else if (k in IMPORT_QUESTIONNAIRE_EXTRA_LABELS)
          label = IMPORT_QUESTIONNAIRE_EXTRA_LABELS[k];
        else continue;
        const value = normalizeImportedValue(raw);
        if (!value || value === "-" || value === "–") continue;
        rows.push({ label: label || k, value });
      }
    }
  }
  return { rows, clickupUrl };
}

// HR-рекрутёр кандидата. В ClickUp это assignee ("Инна HR") и/или папка
// воронки ("Sandbox - Инна"). Имена рекрутёров уникальны (подтверждено
// админом), поэтому матчим по имени и показываем полное ФИО.
const RECRUITER_FULL_NAMES: Record<string, string> = {
  анастасия: "Пивень Анастасия",
  инна: "Инна Кравчук",
  регина: "Регина Рахманкулова",
  мария: "Голикова Мария",
  яна: "Дудкина Яна",
  эльвира: "Ефименко Эльвира",
};

function resolveRecruiter(
  extra: Record<string, unknown> | undefined,
): string | null {
  if (!extra) return null;
  const explicit = normalizeImportedValue(extra.recruiter);
  if (explicit) return explicit;
  const haystacks = [extra.assignees, extra.funnel_folder, extra.funnel_list]
    .map((x) => (typeof x === "string" ? x.toLowerCase() : ""))
    .join(" | ");
  for (const [firstName, fullName] of Object.entries(RECRUITER_FULL_NAMES)) {
    if (haystacks.includes(firstName)) return fullName;
  }
  return null;
}

// Внешняя ссылка на резюме (hh/rabota.by) для архивных импортов: своего AI-резюме
// нет, но у большинства кандидатов ссылка лежит в ответах анкеты прохождений.
const RESUME_URL_RE = /(https?:\/\/(?:www\.)?(?:hh\.ru|rabota\.by)\/resume\/[0-9a-zA-Z]+)/i;

function findExternalResume(card: KanbanCard): string | null {
  const src = card.source_url || "";
  const sm = RESUME_URL_RE.exec(src);
  if (sm) return sm[1];
  const ed = card.extra_data as Record<string, unknown> | undefined;
  const parts = Array.isArray(ed?.participations)
    ? (ed!.participations as Array<Record<string, unknown>>)
    : [];
  for (const p of parts) {
    const anketa = Array.isArray(p.anketa)
      ? (p.anketa as Array<Record<string, unknown>>)
      : [];
    for (const qa of anketa) {
      const m = RESUME_URL_RE.exec(String(qa.answer ?? ""));
      if (m) return m[1];
    }
  }
  return null;
}

const ImportedQuestionnaire = memo(function ImportedQuestionnaire({
  card,
}: {
  card: KanbanCard;
}) {
  const { rows } = getImportedQuestionnaire(card);
  const recruiter = resolveRecruiter(
    card.extra_data as Record<string, unknown> | undefined,
  );
  if (rows.length === 0 && !recruiter) return null;
  return (
    <div className="p-5 max-w-3xl space-y-4">
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
          Анкета кандидата
        </h3>
        {recruiter && (
          <div className="text-xs text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
            Рекрутёр:{" "}
            <span className="font-medium text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
              {recruiter}
            </span>
          </div>
        )}
      </div>
      {rows.length > 0 && (
        <div className="rounded-lg border border-[color:var(--hf-main-200)] overflow-hidden hf-dark-disabled:border-[color:var(--hf-white-alpha-06)]">
          {rows.map((r, i) => (
            <div
              key={i}
              className="grid grid-cols-1 gap-1 border-b border-[color:var(--hf-main-100)] px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(150px,240px)_1fr] sm:gap-4 hf-dark-disabled:border-[color:var(--hf-white-alpha-05)]"
            >
              <div className="text-xs font-medium text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                {r.label}
              </div>
              <div className="whitespace-pre-wrap break-words text-sm text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                {renderAnswer(r.value)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

// ---------- Résumé sources hook ----------
// Загружает файлы кандидата и вычисляет список источников резюме. Один и тот
// же расчёт нужен и панели вкладок (сколько вкладок «Резюме» рисовать), и
// самой вкладке (что показывать) — поэтому вынесен в общий хук.
export function useResumeSources(
  card: KanbanCard,
  refreshKey?: number,
): {
  files: EntityFile[];
  sources: ResumeSource[];
  loading: boolean;
  previewUrls: Record<number, string>;
} {
  const [files, setFiles] = useState<EntityFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [previewUrls, setPreviewUrls] = useState<Record<number, string>>({});

  useEffect(() => {
    setLoading(true);
    getEntityFiles(card.id)
      .then((data) => {
        setFiles(data);
        // Generate preview URLs for image files
        data
          .filter((f) => f.mime_type?.startsWith("image/"))
          .forEach(async (f) => {
            try {
              const blob = await downloadEntityFile(card.id, f.id);
              setPreviewUrls((prev) => ({
                ...prev,
                [f.id]: URL.createObjectURL(blob),
              }));
            } catch {
              /* ignore */
            }
          });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [card.id, refreshKey]);

  const sources: ResumeSource[] = buildResumeSources(
    files,
    card.extra_data as Record<string, unknown> | undefined,
  );

  return { files, sources, loading, previewUrls };
}

// ---------- Текст резюме из формы ----------

/** Резюме, вписанное текстом в форму «Новый кандидат» / «Редактировать». */
function TextResume({ text }: { text: string }) {
  return (
    <div className="pt-[var(--hf-space-xxl)] max-w-[1180px]">
      <div className="rounded-[16px] border border-[color:var(--hf-black-alpha-10)] bg-[var(--hf-white)] px-[var(--hf-space-xxl)] py-[var(--hf-space-xl)] hf-dark-disabled:bg-[var(--hf-white-alpha-04)] hf-dark-disabled:border-[color:var(--hf-white-alpha-08)]">
        <p className="mb-[var(--hf-space-m)] text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-secondary)] text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
          Текст резюме · правится в «Редактировать»
        </p>
        <div className="whitespace-pre-wrap break-words text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-primary)] text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
          {text}
        </div>
      </div>
    </div>
  );
}

// ---------- ResumeTab ----------

const ResumeTab = memo(function ResumeTab({
  card,
  activeIndex,
}: {
  card: KanbanCard;
  activeIndex: number;
}) {
  const { files, sources, loading, previewUrls } = useResumeSources(card);
  const [currentResumeIndex, setCurrentResumeIndex] = useState(0);

  const resumeFiles = files.filter((f) => f.file_type === "resume");
  const pdfFile = resumeFiles.find((f) => f.mime_type === "application/pdf");
  // PDF'ы — новое сверху (для fallback-выбора, когда источник не задан явно).
  const pdfFiles = resumeFiles
    .filter((f) => f.mime_type === "application/pdf")
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  const currentPdf = pdfFiles[0] || pdfFile;
  const imageFiles = resumeFiles.filter((f) =>
    f.mime_type?.startsWith("image/"),
  );
  const resumeDemo = card.extra_data?.resume_demo as ResumeDemoData | undefined;
  const resumeDemos = (
    Array.isArray(card.extra_data?.resume_demos)
      ? (card.extra_data.resume_demos as ResumeDemoData[])
      : resumeDemo
        ? [resumeDemo]
        : []
  ).filter(Boolean);
  const resumeCarouselLength = resumeDemos.length > 0 ? 3 : imageFiles.length || 1;
  const hasPreviousResume = currentResumeIndex > 0;
  const hasNextResume = currentResumeIndex < resumeCarouselLength - 1;

  const mergedFrom = (
    Array.isArray(
      (card.extra_data as Record<string, unknown> | undefined)?.merged_from,
    )
      ? ((card.extra_data as Record<string, unknown>).merged_from as MergedFrom[])
      : []
  );

  useEffect(() => {
    setCurrentResumeIndex(0);
  }, [card.id]);

  useEffect(() => {
    setCurrentResumeIndex((index) =>
      Math.min(index, Math.max(0, resumeCarouselLength - 1)),
    );
  }, [resumeCarouselLength]);

  const handleDownload = async (file: EntityFile) => {
    try {
      const blob = await downloadEntityFile(card.id, file.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.file_name;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Освобождаем URL чуть позже, чтобы Safari/Firefox успели запустить загрузку.
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      console.error("PDF download failed:", err);
      const e = err as Error & { code?: string };
      if (e.code === "file_content_lost") {
        toast.error("Файл утерян на сервере. Перезагрузите резюме кандидата.", {
          duration: 6000,
        });
      } else {
        toast.error("Не удалось скачать файл");
      }
    }
  };

  const handlePrint = () => {
    if (imageFiles.length > 0) {
      const urls = imageFiles.map((f) => previewUrls[f.id]).filter(Boolean);
      if (urls.length === 0) {
        toast.error("Загрузка...");
        return;
      }
      const w = window.open("", "_blank");
      if (w) {
        w.document.write(
          `<html><body style="margin:0">${urls.map((u) => `<img src="${u}" style="width:100%;page-break-after:always"/>`).join("")}</body></html>`,
        );
        w.document.close();
        w.onload = () => w.print();
      }
    } else if (pdfFile) {
      handleDownload(pdfFile);
    } else {
      toast("Нет исходного файла для печати");
    }
  };

  const handleShowText = () => {
    toast("Текст резюме уже показан");
  };

  const handleDemoDownload = () => {
    if (pdfFile) {
      handleDownload(pdfFile);
      return;
    }
    toast("Нет исходного файла для скачивания");
  };

  if (loading) {
    return (
      <div className="space-y-[16px] px-[var(--hf-space-xxl)] py-[24px]">
        <HfSkeletonBlock className="h-[18px] w-[180px] rounded-[var(--hf-radius-xs)]" />
        <HfSkeletonBlock className="h-[720px] w-full rounded-[var(--hf-radius-s)]" />
      </div>
    );
  }

  if (resumeFiles.length === 0 && !resumeDemo) {
    const importedQuestionnaire = getImportedQuestionnaire(card);
    const externalResume = findExternalResume(card);
    // Текст резюме из формы. Без этой ветки кандидат, созданный вручную с
    // «Текстом резюме», показывал заглушку «Резюме ещё не сгенерировано… через
    // Волшебную кнопку», хотя текст лежал в карточке (Мария, 15.10.2026).
    const textSource = sources.find(
      (src): src is Extract<ResumeSource, { kind: "text" }> => src.kind === "text",
    );
    const qMainContent = importedQuestionnaire.rows.length > 0 ? (
      <ImportedQuestionnaire card={card} />
    ) : textSource ? (
      <TextResume text={textSource.text} />
    ) : externalResume ? (
      <div className="p-5 max-w-3xl">
        <div className="bg-[var(--hf-white-alpha-02)] border border-[color:var(--hf-white-alpha-06)] rounded-lg p-8 text-center text-sm min-h-[200px] flex flex-col items-center justify-center gap-3">
          <FileText className="w-8 h-8 opacity-40 text-[var(--hf-cyan-600)]" />
          <p className="text-[var(--hf-main-800)] hf-dark-disabled:text-[var(--hf-white)]">
            Внешнее резюме кандидата
          </p>
          <a
            href={externalResume}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[var(--hf-cyan-600)] text-white hover:bg-[var(--hf-cyan-500)] transition-colors"
          >
            <Eye className="w-4 h-4" /> Открыть на{" "}
            {externalResume.includes("rabota.by") ? "rabota.by" : "hh.ru"}
          </a>
          <p className="text-xs text-[var(--hf-dark-600)] break-all">{externalResume}</p>
        </div>
      </div>
    ) : (
      <div className="p-5 max-w-3xl">
        <div className="bg-[var(--hf-white-alpha-02)] border border-[color:var(--hf-white-alpha-06)] rounded-lg p-8 text-center text-[var(--hf-dark-500)] text-sm min-h-[200px] flex flex-col items-center justify-center gap-2">
          <FileText className="w-8 h-8 opacity-30" />
          <p>Резюме ещё не сгенерировано</p>
          <p className="text-xs text-[var(--hf-dark-600)]">
            Резюме создаётся автоматически после добавления кандидата через
            Волшебную кнопку
          </p>
        </div>
      </div>
    );
    if (mergedFrom.length === 0) return qMainContent;
    return (
      <div className="flex flex-col lg:flex-row gap-4">
        <div className="flex-1 min-w-0">{qMainContent}</div>
        <div className="flex-1 min-w-0 lg:border-l lg:pl-4 border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-06)] space-y-4 p-5">
          {mergedFrom.map((m, i) => {
            // Показываем заголовок «Объединено: …» для КАЖДОГО влитого профиля,
            // чтобы при слиянии 3+ не «терялись» голые PDF/CSV-импорты (без строк
            // анкеты и рекрутёра). Если тела нет — заменяем его короткой подписью,
            // но сам контейнер НЕ прячем.
            const mq = getImportedQuestionnaire({ ...card, extra_data: m.extra_data } as KanbanCard);
            const mRecruiter = resolveRecruiter(m.extra_data as Record<string, unknown> | undefined);
            const hasBody = mq.rows.length > 0 || !!mRecruiter;
            return (
              <div key={m.entity_id ?? i}>
                <div className="mb-2 text-xs text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                  Объединено:{" "}
                  <span className="font-medium text-[var(--hf-main-900)] hf-dark-disabled:text-[var(--hf-white)]">
                    {m.name || "Кандидат"}
                  </span>
                  {m.merged_by_name ? ` · ${m.merged_by_name}` : ""}
                  {m.merged_at ? ` · ${new Date(m.merged_at).toLocaleString("ru")}` : ""}
                </div>
                {hasBody ? (
                  <ImportedQuestionnaire
                    card={{ ...card, name: m.name || card.name, extra_data: m.extra_data } as KanbanCard}
                  />
                ) : (
                  <div className="text-xs italic text-[var(--hf-main-500)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
                    Анкета не заполнена (импорт из PDF/файла).
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Источник резюме выбирается верхними вкладками (по одной на каждое резюме).
  // Внутренней вкладочной полосы здесь больше нет — её роль выполняют вкладки
  // верхнего уровня рядом с «Личные заметки». Резюме — на всю ширину.
  const safeSourceIndex = Math.min(
    activeIndex,
    Math.max(0, sources.length - 1),
  );
  const selectedSource = sources[safeSourceIndex];

  let parsedContent: ReactNode = null;
  if (resumeDemos.length > 0) {
    const currentDemo = resumeDemos[0];
    const currentResumePage = currentResumeIndex + 1;
    const savedAt = currentDemo.saved_at || card.created_at;
    const vacancyTitle = currentDemo.vacancy_title || card.vacancy_name || card.position || "Вакансия";
    const desiredTitle = currentDemo.title || card.position || "Кандидат";
    const salary = currentDemo.salary || card.salary || "";
    const birthDate = card.extra_data?.birth_date as string | undefined;
    const candidateDetails = [
      card.age,
      birthDate ? `родился(лась) ${birthDate}` : "",
    ].filter(Boolean).join(", ");
    const contactLines = [
      formatPhoneDisplay(card.phone),
      card.email,
      card.telegram_username
        ? `telegram: @${card.telegram_username.replace(/^@/, "")}`
        : "",
    ].filter(Boolean);
    const profileLines = [
      card.city ? `Проживает: ${card.city}` : "",
      card.source ? `Источник: ${card.source}` : "",
    ].filter(Boolean);
    const resumeSections = currentDemo.sections || [];
    const renderResumeSection = (
      section: { title: string; lines: string[] },
      index: number,
      className = index === 0 ? "mt-[40px]" : "mt-[34px]",
    ) => (
      <section key={`${section.title}-${index}`} className={className}>
        <h4 className="border-b border-[var(--hf-ui-line)] pb-[2px] text-[length:var(--hf-fs-m)] font-normal leading-[var(--hf-lh-primary)] text-[var(--hf-ui-resume-muted)]">
          {section.title}
        </h4>
        <div className="mt-[10px] space-y-[4px] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)]">
          {(section.lines || []).map((line, lineIndex) => (
            <p key={`${section.title}-${lineIndex}`}>{line}</p>
          ))}
        </div>
      </section>
    );

    parsedContent = (
      <div className="pt-[var(--hf-space-xxl)] max-w-[1180px]">
        <div className="overflow-hidden rounded-[16px] border border-[color:var(--hf-black-alpha-10)] bg-[var(--hf-white)] hf-dark-disabled:bg-[var(--hf-white-alpha-04)] hf-dark-disabled:border-[color:var(--hf-white-alpha-08)]">
          <div className="rounded-t-[16px] bg-[var(--hf-main-50)] px-[var(--hf-space-xxl)] pt-[var(--hf-space-xxl)] pb-[27px] hf-dark-disabled:bg-[var(--hf-white-alpha-03)]">
            <p className="mb-[20px] text-[length:var(--hf-fs-xxs)] leading-[var(--hf-lh-secondary)] text-[var(--hf-main-900)] hf-dark-disabled:text-[color:var(--hf-white-alpha-45)]">
              Сохранено {formatResumeSaved(savedAt)}
            </p>
            <div className="flex items-center gap-[var(--hf-space-s)]">
              <button
                type="button"
                onClick={handleShowText}
                className="hf-resume-action-btn"
              >
                <Type className="hf-resume-action-icon" />
                <span className="hf-resume-action-label">Показать текст</span>
              </button>
              <button
                type="button"
                onClick={handlePrint}
                className="hf-resume-action-btn"
              >
                <Printer className="hf-resume-action-icon" />
                <span className="hf-resume-action-label">Распечатать</span>
              </button>
              <button
                type="button"
                onClick={handleDemoDownload}
                className="hf-resume-action-btn"
              >
                <Download className="hf-resume-action-icon" />
                <span className="hf-resume-action-label">Скачать</span>
              </button>
            </div>
          </div>

          <div className="relative bg-transparent px-[100px] pt-[36px] pb-[58px] hf-dark-disabled:bg-[var(--hf-white-alpha-02)]">
            <button
              type="button"
              aria-label="Предыдущее резюме"
              onClick={() =>
                setCurrentResumeIndex((index) => Math.max(0, index - 1))
              }
              disabled={!hasPreviousResume}
              className={clsx(
                "absolute left-[36px] top-[52%] flex h-[38px] w-[38px] -translate-y-1/2 items-center justify-center rounded-full bg-[var(--hf-white-alpha-90)] shadow-[0_1px_2px_var(--hf-alpha-150)] transition-colors",
                hasPreviousResume
                  ? "text-[var(--hf-ui-resume-arrow)] hover:bg-[var(--hf-white)] hover:text-[var(--hf-main-900)] active:bg-[var(--hf-main-200)]"
                  : "cursor-default text-[var(--hf-ui-resume-arrow-off)] opacity-70",
              )}
            >
              <ChevronLeft className="h-[20px] w-[20px]" />
            </button>
            <button
              type="button"
              aria-label="Следующее резюме"
              onClick={() =>
                setCurrentResumeIndex((index) =>
                  Math.min(resumeCarouselLength - 1, index + 1),
                )
              }
              disabled={!hasNextResume}
              className={clsx(
                "absolute right-[36px] top-[52%] flex h-[38px] w-[38px] -translate-y-1/2 items-center justify-center rounded-full bg-[var(--hf-white-alpha-90)] shadow-[0_1px_2px_var(--hf-alpha-150)] transition-colors",
                hasNextResume
                  ? "text-[var(--hf-ui-resume-arrow)] hover:bg-[var(--hf-white)] hover:text-[var(--hf-main-900)] active:bg-[var(--hf-main-200)]"
                  : "cursor-default text-[var(--hf-ui-resume-arrow-off)] opacity-70",
              )}
            >
              <ChevronRight className="h-[20px] w-[20px]" />
            </button>
            <button
              type="button"
              aria-label="Развернуть"
              className="absolute right-[52px] top-[42px] rounded-[6px] p-[4px] text-[var(--hf-ui-expand-icon)] transition-colors hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-900)] active:bg-[var(--hf-black-alpha-07)]"
            >
              <Maximize2 className="h-[21px] w-[21px]" />
            </button>

            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={currentResumePage}
                initial={{ opacity: 0, x: 28 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -28 }}
                transition={{ duration: 0.18, ease: "easeOut" }}
                className="mx-auto min-h-[880px] w-full max-w-[980px] bg-[var(--hf-white)] text-[var(--hf-main-900)] shadow-[0_12px_30px_var(--hf-alpha-200)]"
              >
              <div className="flex h-[66px] items-center justify-between bg-[var(--hf-ui-divider)] px-[66px] text-[length:var(--hf-fs-xs)] leading-[var(--hf-lh-secondary)] text-[var(--hf-ui-resume-text)]">
                <div>
                  <div>Отклик на вакансию: «{vacancyTitle}»</div>
                  <div className="mt-[4px] text-[length:var(--hf-fs-2xs)] text-[var(--hf-ui-resume-muted)]">
                    {formatResumeSaved(savedAt)}
                  </div>
                </div>
                <span className="inline-flex h-[32px] w-[32px] items-center justify-center rounded-full bg-[var(--hf-red-600)] text-[length:var(--hf-fs-xs)] font-bold text-[var(--hf-white)]">
                  hh
                </span>
              </div>

              <div className="px-[66px] pb-[64px] pt-[34px]">
                {currentResumePage === 1 ? (
                  <>
                <div className="flex gap-[var(--hf-space-xxl)]">
                  {card.photo_url ? (
                    <img
                      src={card.photo_url}
                      alt=""
                      className="mt-[2px] h-[92px] w-[92px] flex-shrink-0 rounded-[2px] object-cover"
                    />
                  ) : (
                    <div className="mt-[2px] flex h-[92px] w-[92px] flex-shrink-0 items-center justify-center rounded-[2px] bg-[var(--hf-ui-avatar-dark)] text-[24px] font-semibold text-[var(--hf-ui-text-avatar-blue)]">
                      {getInitials(card.name)}
                    </div>
                  )}
                  <div className="min-w-0">
                    <h3 className="text-[40px] font-bold leading-[46px] tracking-normal">
                      {card.name}
                    </h3>
                    <p className="mt-[2px] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)] text-[var(--hf-ui-resume-secondary)]">
                      {candidateDetails}
                    </p>
                    <div className="mt-[16px] space-y-[1px] text-[length:var(--hf-fs-s)] leading-[21px]">
                      {contactLines.map((line) => (
                        <p key={line}>{line}</p>
                      ))}
                    </div>
                    <div className="mt-[18px] space-y-[1px] text-[length:var(--hf-fs-s)] leading-[21px]">
                      {profileLines.map((line) => (
                        <p key={line}>{line}</p>
                      ))}
                    </div>
                  </div>
                </div>

                <section className="mt-[42px]">
                  <h4 className="border-b border-[var(--hf-ui-line)] pb-[2px] text-[length:var(--hf-fs-m)] font-normal leading-[var(--hf-lh-primary)] text-[var(--hf-ui-resume-muted)]">
                    Желаемая должность и зарплата
                  </h4>
                  <div className="mt-[8px] flex items-start justify-between gap-[var(--hf-space-xxl)]">
                    <div className="text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)]">
                      <p className="text-[20px] font-bold leading-[26px]">
                        {desiredTitle}
                      </p>
                      <p className="mt-[6px]">Специализации:</p>
                      <p className="pl-[30px]">— Тестировщик</p>
                      <p className="mt-[6px]">
                        Тип занятости: полная занятость
                      </p>
                      <p>Формат работы: на месте работодателя</p>
                      <p>
                        Желательное время в пути до работы: не имеет значения
                      </p>
                    </div>
                    <div className="flex-shrink-0 pt-[2px] text-right">
                      {salary ? (
                        <>
                          <span className="text-[24px] font-bold leading-[30px]">
                            {salary}
                          </span>
                          <span className="ml-[4px] text-[length:var(--hf-fs-xxs)] leading-[18px]">
                            на руки
                          </span>
                        </>
                      ) : null}
                    </div>
                  </div>
                </section>

                {resumeSections
                  .slice(0, 2)
                  .map((section, index) => renderResumeSection(section, index))}

                  </>
                ) : currentResumePage === 2 ? (
                  <>
                    {resumeSections
                      .slice(2)
                      .map((section, index) =>
                        renderResumeSection(
                          section,
                          index + 2,
                          index === 0 ? "" : "mt-[34px]",
                        ),
                      )}
                  </>
                ) : (
                  <>
                    <section>
                      <h4 className="border-b border-[var(--hf-ui-line)] pb-[2px] text-[length:var(--hf-fs-m)] font-normal leading-[var(--hf-lh-primary)] text-[var(--hf-ui-resume-muted)]">
                        Данные резюме
                      </h4>
                      <div className="mt-[16px] space-y-[8px] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)]">
                        <p>{card.name}</p>
                        {card.position ? <p>{card.position}</p> : null}
                        {card.company ? <p>{card.company}</p> : null}
                        {card.source ? <p>Источник: {card.source}</p> : null}
                      </div>
                    </section>
                    <section className="mt-[42px]">
                      <h4 className="border-b border-[var(--hf-ui-line)] pb-[2px] text-[length:var(--hf-fs-m)] font-normal leading-[var(--hf-lh-primary)] text-[var(--hf-ui-resume-muted)]">
                        Резюме обновлено {formatResumeSaved(savedAt)}
                      </h4>
                      <div className="mt-[18px] text-[length:var(--hf-fs-s)] leading-[var(--hf-lh-field)]">
                        <p>{card.name} • Резюме обновлено {formatResumeSaved(savedAt)}</p>
                      </div>
                    </section>
                  </>
                )}
                <div className="mt-[36px] text-right text-[length:var(--hf-fs-2xs)] leading-[18px] text-[var(--hf-ui-resume-muted)]">
                  Страница {currentResumePage}/{resumeCarouselLength}
                </div>
              </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    );
  }

  // Контент файлового резюме (PDF / сканы / fallback). Принимает конкретный
  // PDF к показу, чтобы вкладка-источник «pdf» открывала ИМЕННО свой файл.
  const buildFileContent = (pdf: EntityFile | undefined) => (
    <div className="py-hf-l max-w-[1180px]">
      <p className="text-hf-3xs text-[var(--hf-main-600)] hf-dark-disabled:text-[color:var(--hf-white-alpha-40)] mb-hf-m">
        Сохранено{" "}
        {formatDateFull(resumeFiles[0]?.created_at || card.created_at)}
      </p>
      <div className="flex items-center gap-hf-s mb-hf-l">
        {card.source_url && (
          <button
            onClick={() => window.open(card.source_url!, "_blank")}
            className="inline-flex items-center gap-1.5 h-[30px] px-hf-m border border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-08)] rounded-hf-s text-hf-3xs text-[var(--hf-main-700)] hf-dark-disabled:text-[color:var(--hf-white-alpha-55)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
          >
            <Eye className="w-3.5 h-3.5" /> Открыть источник
          </button>
        )}
        <button
          onClick={handlePrint}
          className="inline-flex items-center gap-1.5 h-[30px] px-hf-m border border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-08)] rounded-hf-s text-hf-3xs text-[var(--hf-main-700)] hf-dark-disabled:text-[color:var(--hf-white-alpha-55)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
        >
          <Printer className="w-3.5 h-3.5" /> Распечатать
        </button>
        {pdf && (
          <button
            onClick={() => handleDownload(pdf)}
            className="inline-flex items-center gap-1.5 h-[30px] px-hf-m border border-[color:var(--hf-main-200)] hf-dark-disabled:border-[color:var(--hf-white-alpha-08)] rounded-hf-s text-hf-3xs text-[var(--hf-main-700)] hf-dark-disabled:text-[color:var(--hf-white-alpha-55)] hover:text-[var(--hf-main-900)] hf-dark-disabled:hover:text-[var(--hf-white)] transition-colors"
          >
            <Download className="w-3.5 h-3.5" /> Скачать PDF
          </button>
        )}
      </div>
      {/* Resume preview — show JPEG pages */}
      {imageFiles.length > 0 && !pdf ? (
        <div className="space-y-3">
          {imageFiles.map((f) => (
            <div
              key={f.id}
              className="bg-[var(--hf-white-alpha-02)] border border-[color:var(--hf-white-alpha-06)] rounded-lg overflow-hidden"
            >
              {previewUrls[f.id] ? (
                <img
                  src={previewUrls[f.id]}
                  alt={f.file_name}
                  className="w-full"
                />
              ) : (
                <div className="p-8 text-center text-[var(--hf-dark-500)] text-sm">
                  Загрузка...
                </div>
              )}
            </div>
          ))}
        </div>
      ) : pdf ? (
        <div className="space-y-2">
          {/* #toolbar=0&navpanes=0 — прячем редакторскую панель Chrome PDF-вьюера: чистый просмотр. */}
          <iframe
            key={pdf.id}
            src={`/api/entities/${card.id}/files/${pdf.id}/download#toolbar=0&navpanes=0`}
            title={pdf.file_name}
            className="w-full min-h-[760px] rounded-lg border border-[color:var(--hf-white-alpha-06)] bg-white"
          />
          <div className="flex items-center justify-between gap-2 px-1 text-xs text-[var(--hf-dark-500)]">
            <span className="truncate">
              {pdf.file_name} · {(pdf.file_size / 1024).toFixed(0)} КБ
              {pdf.created_at ? ` · загружено ${formatDateFull(pdf.created_at)}` : ""}
            </span>
            <button
              onClick={() => handleDownload(pdf)}
              className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 bg-[var(--hf-accent-bg-20)] text-[var(--hf-accent)] rounded-lg hover:bg-[var(--hf-accent-bg-30)] transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> Скачать
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-[var(--hf-white-alpha-02)] border border-[color:var(--hf-white-alpha-06)] rounded-lg p-8 text-center text-[var(--hf-dark-500)] text-sm">
          {resumeFiles.map((f) => (
            <p key={f.id}>{f.file_name}</p>
          ))}
        </div>
      )}
    </div>
  );

  // Контент выбранного источника. Когда источников нет — buildFileContent(undefined)
  // даёт прежний fallback со списком имён файлов.
  let selectedContent: ReactNode;
  if (selectedSource?.kind === "parsed") {
    selectedContent = parsedContent;
  } else if (selectedSource?.kind === "pdf") {
    selectedContent = buildFileContent(selectedSource.file);
  } else if (selectedSource?.kind === "images") {
    selectedContent = buildFileContent(undefined);
  } else if (selectedSource?.kind === "text") {
    selectedContent = <TextResume text={selectedSource.text} />;
  } else {
    selectedContent = buildFileContent(currentPdf);
  }

  // Резюме — на всю ширину, без внутренней полосы вкладок и боковой панели.
  return selectedContent;
});

export default ResumeTab;

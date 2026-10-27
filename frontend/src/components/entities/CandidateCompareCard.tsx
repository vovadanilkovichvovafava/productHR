import { useEffect, useRef, useState, type ReactNode } from "react";
import type { KanbanCard } from "@/services/api/candidates";
import type { EntityWithRelations } from "@/types";
import { STATUS_LABELS } from "@/types";
import { sanitizeHtml } from "@/utils/sanitizeHtml";
import { CompareResumePreview } from "./CompareResumePreview";
import { pickTelegram } from "./candidateDetail/model";
import { getEntityActivity, type VacancyActivityBlock } from "@/services/api/entities";
import { parseServerDate } from "@/utils/date";
import { STAGE_CHIP_BRIGHT_BY_STAGE, STAGE_LABEL_BY_STAGE } from "@/constants/hrStages";

const stageLabel = (stage: string): string =>
  (STAGE_LABEL_BY_STAGE as Record<string, string>)[stage] || stage;
import {
  getPriorRejections,
  priorRejectionWhere,
  type PriorRejection,
} from "@/components/candidates/priorRejection";

/**
 * Окно сравнения дублей: данные двух анкет (Side и билдеры), сверка полей
 * (matchKindOf по сигналам бэка) и сама таблица «поле в строку» (CompareTable,
 * с 22.10.2026 вместо двух независимых карточек рядом).
 */

export interface ResumeDemo {
  title?: string;
  subtitle?: string;
  salary?: string;
  vacancy_title?: string;
  sections?: Array<{ title?: string; lines?: string[] }>;
}

export interface TimelineEvent {
  date?: string;
  title?: string;
}

// Резюме-текста часто нет (анонимные hh-анкеты из расширения), но есть
// структурные поля — показываем их как резюме, чтобы блок не был пустым.
export type ResumeExtra = {
  experience: string;
  skills: string;
  languages: string;
  education: string;
};

export type Side = {
  name: string;
  photo: string;
  position: string;
  company: string;
  phone: string;
  email: string;
  telegram: string;
  age: string;
  birthDate: string;
  city: string;
  salary: string;
  experience: string;
  source: string;
  tags: string;
  statusLabel: string;
  isRejected: boolean;
  rejectReason: string;
  rejectedAt: string;
  history: TimelineEvent[];
  resumes: ResumeDemo[];
  resumeText: string;
  resumeExtra: ResumeExtra;
  notes: Array<{ text?: string; author?: string; date?: string }>;
  /** Навыки списком — окно подсвечивает общие. */
  skills: string[];
  /** Последние места работы строками «должность | компания | период». */
  jobs: string[];
  /** Откуда резюме: ссылка hh/LinkedIn (если добавлен расширением). */
  sourceUrl: string;
};

export type FieldKey =
  | "phone" | "email" | "telegram" | "birthDate" | "age" | "city"
  | "salary" | "experience" | "source" | "tags";

/** Насколько совпало поле: точно (идентификатор) или частично (мягкий сигнал). */
export type MatchKind = "exact" | "partial" | null;

// String() coercion: значения полей (age/salary/experience) из API могут прийти
// числом, а не строкой — без приведения .trim() падает «(e||"").trim is not a function».
const norm = (v: unknown) => String(v ?? "").trim().toLowerCase();
const normPhone = (v: unknown) => String(v ?? "").replace(/\D/g, "").slice(-10);
const normTg = (v: unknown) => String(v ?? "").trim().replace(/^@/, "").toLowerCase();
/** Дата рождения из extra_data в едином виде ДД.ММ.ГГГГ (источники пишут
 *  и «1990-05-14», и «14.05.1990»). */
function birthParts(birthDate?: string): { y: number; m: number; d: number } | null {
  if (!birthDate) return null;
  const iso = /(\d{4})-(\d{2})-(\d{2})/.exec(birthDate);
  if (iso) return { y: +iso[1], m: +iso[2], d: +iso[3] };
  const ru = /(\d{2})[.\/](\d{2})[.\/](\d{4})/.exec(birthDate);
  if (ru) return { y: +ru[3], m: +ru[2], d: +ru[1] };
  return null;
}

function formatBirth(birthDate?: string): string {
  const p = birthParts(birthDate);
  if (!p) return "";
  return `${String(p.d).padStart(2, "0")}.${String(p.m).padStart(2, "0")}.${p.y}`;
}

function computeAge(birthDate?: string): string {
  const p = birthParts(birthDate);
  if (!p) return "";
  const today = new Date();
  let age = today.getFullYear() - p.y;
  if ((today.getMonth() + 1) * 100 + today.getDate() < p.m * 100 + p.d) age -= 1;
  return age >= 14 && age <= 100 ? `${age} лет` : "";
}

function statusLabelOf(key?: string): string {
  if (!key) return "";
  const map = STATUS_LABELS as Record<string, string>;
  return map[key] || key;
}

function timelineFrom(extra: Record<string, unknown> | undefined): TimelineEvent[] {
  const ev = extra?.timeline_events;
  return Array.isArray(ev) ? (ev as TimelineEvent[]) : [];
}

function rejectedDate(history: TimelineEvent[]): string {
  const ev = history.find((e) => (e.title || "").toLowerCase().includes("отказ"));
  return ev?.date || "";
}

function resumesFrom(extra: Record<string, unknown> | undefined): ResumeDemo[] {
  if (!extra) return [];
  if (Array.isArray(extra.resume_demos)) return (extra.resume_demos as ResumeDemo[]).filter(Boolean);
  if (extra.resume_demo) return [extra.resume_demo as ResumeDemo];
  return [];
}

function joinStrs(v: unknown, sep = ", "): string {
  if (Array.isArray(v)) return (v as unknown[]).filter((x) => typeof x === "string" && x.trim()).join(sep);
  return typeof v === "string" ? v : "";
}

// Текст резюме для сравнения. Импортированные (архивные) кандидаты из CSV/ClickUp
// не имеют resume_text — их резюме лежит в description (текст формы ClickUp) и в
// cf:* полях (как читает собственная карточка, ResumeTab). Без этого фолбэка
// правая (архивная) анкета в сравнении показывала «—», хотя данные есть.
function resumeTextFrom(extra: Record<string, unknown> | undefined): string {
  const e = extra || {};
  if (typeof e.resume_text === "string" && e.resume_text.trim()) return e.resume_text;
  if (typeof e.description === "string" && e.description.trim()) return e.description;
  const cf = Object.entries(e)
    .filter(([k, v]) => k.startsWith("cf:") && typeof v === "string" && (v as string).trim())
    .map(([k, v]) => `${k.slice(3).trim()}: ${v}`);
  return cf.join("\n");
}

// Собираем «резюме из структурных полей» (опыт/навыки/языки/образование) —
// fallback, когда полноценного resume_text/resume_demos нет.
function resumeExtraFrom(extra: Record<string, unknown> | undefined): ResumeExtra {
  const e = extra || {};
  const exp = [
    typeof e.experience_summary === "string" ? e.experience_summary : "",
    joinStrs(e.experience_descriptions, "\n\n"),
  ].filter(Boolean).join("\n\n");
  return {
    experience: exp,
    skills: joinStrs(e.skills),
    languages: joinStrs(e.languages),
    education: joinStrs(e.education, "; "),
  };
}

function skillsFrom(extra: Record<string, unknown>): string[] {
  const v = extra.skills;
  return Array.isArray(v) ? (v as unknown[]).filter((x): x is string => typeof x === "string" && !!x.trim()) : [];
}

function jobsFrom(extra: Record<string, unknown>): string[] {
  const v = extra.experience_summary;
  return typeof v === "string" ? v.split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 3) : [];
}

function notesFrom(extra: Record<string, unknown> | undefined): Array<{ text?: string; author?: string; date?: string }> {
  const ns = extra?.notes;
  if (!Array.isArray(ns)) return [];
  return (ns as Array<Record<string, unknown>>)
    .filter((n) => n && n.text)
    .map((n) => {
      let date = (n.date as string) || "";
      // Убираем timezone offset: "2026-06-24T22:18:32.047491+00:00" → "2026-06-24T22:18:32"
      date = date.replace(/\.\d+[+-]\d{2}:\d{2}$/, "");
      return { text: n.text as string, author: n.author_name as string, date };
    });
}

export function sideFromCard(card: KanbanCard, statusKey?: string): Side {
  const extra = (card.extra_data || {}) as Record<string, unknown>;
  const history = timelineFrom(extra);
  const isRejected = statusKey === "rejected";
  return {
    name: card.name || "",
    photo: card.photo_url || ((extra.photo_url as string) || ""),
    position: card.position || "",
    company: card.company || "",
    phone: card.phone || "",
    email: card.email || "",
    telegram: pickTelegram([card.telegram_username, ...(card.telegram_usernames || [])]) || "",
    age: card.age ? String(card.age) : computeAge(extra.birth_date as string | undefined),
    birthDate: formatBirth(extra.birth_date as string | undefined),
    city: card.city || ((extra.city as string) || ""),
    salary: card.salary ? String(card.salary) : "",
    experience: card.total_experience ? String(card.total_experience) : ((extra.total_experience as string) || ""),
    source: card.source || ((extra.source as string) || ""),
    tags: ((card.tags as string[] | undefined) || []).join(", "),
    statusLabel: statusLabelOf(statusKey),
    isRejected,
    rejectReason: (card.rejection_reason as string) || ((extra.rejection_reason as string) || ""),
    rejectedAt: isRejected ? rejectedDate(history) : "",
    history,
    resumes: resumesFrom(extra),
    resumeText: resumeTextFrom(extra),
    resumeExtra: resumeExtraFrom(extra),
    notes: notesFrom(extra),
    skills: skillsFrom(extra),
    jobs: jobsFrom(extra),
    sourceUrl: card.source_url || String(extra.source_url || ""),
  };
}

export function sideFromEntity(e: EntityWithRelations): Side {
  const ent = e as unknown as Record<string, unknown>;
  const extra = (e.extra_data || {}) as Record<string, unknown>;
  const history = timelineFrom(extra);
  const statusKey = (ent.status as string) || "";
  const isRejected = statusKey === "rejected";
  const lo = e.expected_salary_min;
  const hi = e.expected_salary_max;
  const cur = e.expected_salary_currency || "";
  let salary = "";
  if (lo && hi) salary = `${lo.toLocaleString()}–${hi.toLocaleString()} ${cur}`.trim();
  else if (lo) salary = `от ${lo.toLocaleString()} ${cur}`.trim();
  else if (hi) salary = `до ${hi.toLocaleString()} ${cur}`.trim();
  return {
    name: e.name || "",
    photo: (extra.photo_url as string) || "",
    position: e.position || "",
    company: e.company || "",
    phone: e.phone || (e.phones && e.phones[0]) || "",
    email: e.email || (e.emails && e.emails[0]) || "",
    telegram: pickTelegram(e.telegram_usernames) || "",
    age: (extra.age as string) || computeAge(extra.birth_date as string | undefined),
    birthDate: formatBirth(extra.birth_date as string | undefined),
    city: (ent.city as string) || ((extra.city as string) || ""),
    salary,
    experience: ((ent.total_experience as string) || (extra.total_experience as string) || ""),
    source: (ent.source as string) || ((extra.source as string) || ""),
    tags: ((ent.tags as string[] | undefined) || []).join(", "),
    statusLabel: statusLabelOf(statusKey),
    isRejected,
    rejectReason: (ent.rejection_reason as string) || ((extra.rejection_reason as string) || ""),
    rejectedAt: isRejected ? rejectedDate(history) : "",
    history,
    resumes: resumesFrom(extra),
    resumeText: resumeTextFrom(extra),
    resumeExtra: resumeExtraFrom(extra),
    notes: notesFrom(extra),
    skills: skillsFrom(extra),
    jobs: jobsFrom(extra),
    sourceUrl: String(extra.source_url || ""),
  };
}

// Поле сигнала с бэка (duplicate_matcher.DupSignal.field) → поле карточки.
const SIGNAL_FIELD_TO_SIDE: Record<string, FieldKey | "name"> = {
  name: "name",
  email: "email",
  phone: "phone",
  telegram: "telegram",
  birth_date: "birthDate",
  age: "age",
  city: "city",
  source: "source",
};

export type DupSignalLike = { field: string; label: string; identity: boolean };

/**
 * Насколько совпало поле — по сигналам БЭКА, а не по сравнению строк на фронте.
 *
 * ВИД подсветки отвечает на вопрос «значения одинаковые?», а не «насколько
 * сильный это признак»: у пары на 83% сигнал «совпал телефон» означал совпадение
 * последних 7 цифр при РАЗНЫХ номерах (+7 495… и +7 916…) — такое поле красим
 * пунктиром, а одинаковые дату рождения и город — сплошной заливкой, как раньше.
 * Силу признака (идентификатор / косвенный) показывает блок «почему считаем
 * дублем», а не подсветка. Фолбэк на matchSide работает, пока сигналов нет.
 */
export function matchKindOf(
  signals: DupSignalLike[] | undefined,
  key: FieldKey | "name",
  sameValue: () => boolean,
): MatchKind {
  if (signals && signals.length > 0) {
    const hit = signals.find((s) => SIGNAL_FIELD_TO_SIDE[s.field] === key);
    if (!hit) return null;
    // Контакт с бэка (телефон по E.164, почта, Telegram) — совпадение, даже
    // если написан по-разному: «80291234567» и «+375291234567» — один номер.
    // ФИО бэк сводит с транслитом и опечаткой, поэтому ✓ только при той же
    // фамилии и имени; «Алина» / «Алиса» — ≈ (похоже), а не ✓.
    if (hit.identity && key !== "name") return "exact";
    return sameValue() ? "exact" : "partial";
  }
  return sameValue() ? "exact" : null;
}

// Совпадение поля между двумя сторонами: телефон через normPhone, telegram через
// normTg, остальное — равенство norm. false, если любая из сторон отсутствует.
export function matchSide(left: Side, right: Side | null, key: FieldKey | "name"): boolean {
  if (!right) return false;
  const a = (left as unknown as Record<string, string>)[key];
  const b = (right as unknown as Record<string, string>)[key];
  if (!a || !b) return false;
  if (key === "phone") return normPhone(a).length > 0 && normPhone(a) === normPhone(b);
  if (key === "telegram") return normTg(a) === normTg(b);
  if (key === "name") {
    // Фамилия + имя, порядок и отчество не важны: «Демидова Алина» =
    // «Демидова Алина Игоревна» = «Алина Демидова».
    const two = (v: string) => norm(v).replace(/ё/g, "е").split(/\s+/).slice(0, 2).sort().join(" ");
    return two(a) === two(b);
  }
  return norm(a) === norm(b);
}

function initialsOf(name: string) {
  return name.split(" ").filter(Boolean).slice(0, 2).map((s) => s[0]).join("").toUpperCase();
}

// Отказы ЭТОЙ анкеты — воронки (когда, кто, с какого этапа, комментарий,
// причина), отказ вне воронок, статус прохождения ClickUp. До 22.10.2026 блок
// читал extra_data.timeline_events, которого не пишет никто, и строка
// «отклонён {дата}» не появлялась никогда; причина у второй анкеты тоже не
// доходила — она лежит у заявки, а не у карточки.
function useOwnRejections(entityId?: number): PriorRejection[] {
  const [items, setItems] = useState<PriorRejection[]>([]);
  useEffect(() => {
    if (!entityId) return;
    let alive = true;
    getPriorRejections(entityId)
      .then((list) => alive && setItems(list.filter((r) => r.entity_id === entityId)))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [entityId]);
  return items;
}

function NotesList({ notes }: { notes: Side["notes"] }) {
  if (notes.length === 0) return <div className="text-xs text-slate-300">нет</div>;
  return (
    <div className="space-y-1.5">
      {notes.map((n, i) => (
        <div key={i} className="rounded-lg bg-slate-50 p-2 text-xs">
          <div
            className="text-slate-800 whitespace-pre-wrap hf-rich-content"
            dangerouslySetInnerHTML={{ __html: sanitizeHtml(n.text) }}
          />
          <div className="text-slate-400 mt-1">{[n.author, n.date?.replace("T", " ").slice(0, 16)].filter(Boolean).join(" · ")}</div>
        </div>
      ))}
    </div>
  );
}

// Фото из hh — временные ссылки, протухают: на ошибку показываем инициалы.
function Avatar({ photo, name, muted }: { photo: string; name: string; muted?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (photo && !failed) {
    return (
      <img src={photo} alt="" className="h-9 w-9 rounded-full object-cover shrink-0" onError={() => setFailed(true)} />
    );
  }
  return (
    <div
      className={`h-9 w-9 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 ${
        muted ? "bg-slate-100 text-slate-500" : "bg-[#bfeeff] text-[#0b6f9a]"
      }`}
    >
      {initialsOf(name) || "?"}
    </div>
  );
}

export type SystemHrTag = {
  hr_id: number;
  name: string;
  vacancy_id?: number;
  vacancy_title?: string;
};

/** Одна сторона сравнения: данные + откуда они. */
export type CompareSide = {
  side: Side;
  entityId: number;
  caption: string;
  archived?: boolean;
  vacancies?: SystemHrTag[];
  extraData?: Record<string, unknown>;
  /** Когда и кем добавлена — строка «Добавлена» группы «У нас». */
  createdAt?: string | null;
  createdBy?: string | null;
};

type RowKey = FieldKey | "name" | "position";

// Строки по группам. Пустая у обеих сторон строка не рисуется.
const GROUPS: { title: string; rows: { key: RowKey; label: string }[] }[] = [
  {
    title: "Личность и контакты",
    rows: [
      { key: "name", label: "ФИО" },
      { key: "birthDate", label: "Дата рождения" },
      { key: "age", label: "Возраст" },
      { key: "city", label: "Город" },
      { key: "phone", label: "Телефон" },
      { key: "email", label: "Почта" },
      { key: "telegram", label: "Telegram" },
    ],
  },
  {
    title: "Работа",
    rows: [
      { key: "position", label: "Должность" },
      { key: "experience", label: "Стаж" },
      { key: "salary", label: "Зарплата" },
    ],
  },
];

function valueOf(side: Side, key: RowKey): string {
  if (key === "position") return [side.position, side.company].filter(Boolean).join(" · ");
  return String((side as unknown as Record<string, unknown>)[key] ?? "");
}

// Название поля для короткой причины в карусели и строке-выводе.
const SIGNAL_WORD: Record<string, string> = {
  name: "имя", phone: "телефон", email: "почта", telegram: "Telegram",
  birth_date: "дата рождения", age: "возраст", city: "город",
  source: "ссылка на резюме", resume_text: "текст резюме", company: "компания",
};

export function signalWords(signals?: DupSignalLike[]): string {
  return [...new Set((signals || []).map((sg) => SIGNAL_WORD[sg.field] || sg.label))].join(" + ");
}

function useActivity(entityId?: number): VacancyActivityBlock[] {
  const [blocks, setBlocks] = useState<VacancyActivityBlock[]>([]);
  useEffect(() => {
    if (!entityId) return;
    let alive = true;
    setBlocks([]);
    getEntityActivity(entityId).then((b) => alive && setBlocks(b || [])).catch(() => {});
    return () => {
      alive = false;
    };
  }, [entityId]);
  return blocks;
}

function shortDate(iso?: string | null): string {
  if (!iso) return "";
  const d = parseServerDate(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru", { day: "numeric", month: "short", year: "numeric" }).replace(" г.", "");
}

function StageChip({ stage }: { stage: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STAGE_CHIP_BRIGHT_BY_STAGE[stage] || "bg-[var(--hf-status-gray)] text-[#111827]"}`}>
      {stageLabel(stage)}
    </span>
  );
}

function FunnelsCell({ blocks, fallback }: { blocks: VacancyActivityBlock[]; fallback: Side }) {
  if (!blocks.length) {
    return (
      <div className="flex items-center gap-1.5">
        {fallback.statusLabel && (
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${fallback.isRejected ? "bg-red-100 text-red-800" : "bg-blue-100 text-blue-800"}`}>
            {fallback.statusLabel}
          </span>
        )}
        <span className="text-slate-400">не в воронке</span>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      {blocks.map((b) => (
        <div key={b.application_id} className="flex flex-wrap items-center gap-1.5">
          <StageChip stage={b.current_stage} />
          <span className="text-slate-800">{b.vacancy_title}</span>
          <span className="text-[11px] text-slate-400">{shortDate(b.last_stage_change_at || b.applied_at)}</span>
        </div>
      ))}
    </div>
  );
}

function HistoryCell({ blocks }: { blocks: VacancyActivityBlock[] }) {
  const withEvents = blocks.filter((b) => b.events.length);
  if (!withEvents.length) return <span className="text-slate-300">—</span>;
  return (
    <div className="space-y-1.5 text-[12px]">
      {withEvents.map((b) => {
        const evs = [...b.events].sort((x, y) => x.created_at.localeCompare(y.created_at));
        const last = evs[evs.length - 1];
        return (
          <div key={b.application_id}>
            {withEvents.length > 1 && <div className="text-[11px] text-slate-400">{b.vacancy_title}</div>}
            <div className="text-slate-700">
              {evs.map((e, i) => (
                <span key={e.id} className={e.to_stage === "rejected" ? "text-red-700 font-semibold" : ""}>
                  {i ? " → " : ""}{stageLabel(e.to_stage)}
                </span>
              ))}
            </div>
            {last?.comment && last.comment !== "Первичная заявка" && (
              <div className={last.to_stage === "rejected" ? "text-red-700" : "text-slate-500"}>
                {last.changed_by_name ? `${last.changed_by_name}: ` : ""}«{last.comment}»
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function RejectionCell({ items }: { items: PriorRejection[] }) {
  if (!items.length) return <span className="text-slate-300">нет</span>;
  return (
    <div className="space-y-1 text-[12px]" style={{ color: "#791f1f" }}>
      {items.slice(0, 2).map((r, i) => (
        <div key={i}>
          <b className="font-semibold">{priorRejectionWhere(r)}</b>
          {r.comment && <div style={{ color: "#a32d2d" }}>«{r.comment}»</div>}
          {r.reason && <div style={{ color: "#a32d2d" }}>Причина: {r.reason}</div>}
        </div>
      ))}
      {items.length > 2 && <div>и ещё {items.length - 2}</div>}
    </div>
  );
}

function SkillsCell({ mine, other }: { mine: string[]; other: string[] }) {
  if (!mine.length) return <span className="text-slate-300">нет</span>;
  const otherSet = new Set(other.map((x) => x.toLowerCase()));
  const sorted = [...mine].sort((a, b) => Number(otherSet.has(b.toLowerCase())) - Number(otherSet.has(a.toLowerCase())));
  return (
    <div className="flex flex-wrap gap-1">
      {sorted.slice(0, 12).map((sk) => (
        <span
          key={sk}
          className={`rounded-full px-2 py-0.5 text-[11px] ${otherSet.has(sk.toLowerCase()) ? "bg-[#eaf3de] text-[#27500a] font-semibold" : "bg-slate-100 text-slate-600"}`}
        >
          {sk}
        </span>
      ))}
      {sorted.length > 12 && <span className="text-[11px] text-slate-400">+{sorted.length - 12}</span>}
    </div>
  );
}

// Отказ — у той анкеты, где он был, прямо у имени (владелец, 24.10.2026:
// строка «слева отказ …» в выводе заставляла соображать, где это «слева»).
function SideHead({ s, rejection }: { s: CompareSide; rejection?: PriorRejection }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <Avatar photo={s.side.photo} name={s.side.name} muted={s.caption !== "Открыта сейчас"} />
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="font-semibold text-slate-900 truncate" title={s.side.name}>{s.side.name || "—"}</span>
          {rejection && (
            <span className="shrink-0 rounded-full px-2 py-[1px] text-[11px] font-semibold" style={{ background: "#fdecec", color: "#a32d2d" }}>
              {rejection.kind === "no_show" ? "Не пришёл" : "Отказ"}{rejection.date ? ` · ${shortDate(rejection.date)}` : ""}
            </span>
          )}
        </div>
        <div className="text-[11px] text-slate-400">
          {s.caption} · ID {s.entityId}
          {s.archived && <span className="ml-1 rounded bg-slate-100 px-1 text-slate-500">архив</span>}
        </div>
      </div>
    </div>
  );
}

// «a, b и c» — вывод сравнения читается одним предложением.
function listRu(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} и ${items[items.length - 1]}`;
}

// Подпись признака с сервера → кусок фразы: «та же компания + похожие навыки»
// → «та же компания и похожие навыки», «совпадает (100%)» → «совпадает на 100%».
function signalPhrase(label: string): string {
  return label.toLowerCase().replace(/\s*\+\s*/g, " и ").replace(/\s*\((\d+)%\)/g, " на $1%");
}

export function compareVerdictText(parts: {
  same: string[];
  alike: string[];
  extra: string[];
  diff: string[];
}): string {
  const clauses: string[] = [];
  if (parts.same.length) clauses.push(`${parts.same.length > 1 ? "совпадают" : "совпадает"} ${listRu(parts.same)}`);
  if (parts.alike.length) clauses.push(`похоже: ${listRu(parts.alike)}`);
  clauses.push(...parts.extra.map(signalPhrase));
  const sentences: string[] = [];
  if (clauses.length) sentences.push(clauses.join("; "));
  if (parts.diff.length) sentences.push(`отличается: ${listRu(parts.diff)}`);
  return sentences.map((t) => `${t.charAt(0).toUpperCase()}${t.slice(1)}.`).join(" ");
}

const GRID = "grid grid-cols-[112px_minmax(0,1fr)_32px_minmax(0,1fr)]";

function Mark({ kind, differs }: { kind: MatchKind; differs?: boolean }) {
  const title = kind === "exact" ? "Совпадает" : kind === "partial" ? "Похоже — сверьте значения" : differs ? "Отличается" : undefined;
  return (
    <div className="text-center text-sm pt-2" title={title}>
      {kind === "exact" ? <span className="text-[#3b6d11]">✓</span>
        : kind === "partial" ? <span className="text-amber-600">≈</span>
        : differs ? <span className="text-slate-300">≠</span> : null}
    </div>
  );
}

function Row({ label, a, b, kind = null, differs, tone }: {
  label: string;
  a: ReactNode;
  b: ReactNode;
  kind?: MatchKind;
  differs?: boolean;
  tone?: string;
}) {
  return (
    <div className={`${GRID} border-t border-slate-100 text-[13px] ${kind === "partial" ? "bg-amber-50" : tone || ""}`}>
      <div className="px-3 py-2 text-[12px] text-slate-400">{label}</div>
      <div className="px-3 py-2 min-w-0 break-words">{a}</div>
      <Mark kind={kind} differs={differs} />
      <div className="px-3 py-2 min-w-0 break-words">{b}</div>
    </div>
  );
}

const empty = <span className="text-slate-300">нет</span>;

/**
 * Окно сравнения дублей — ТАБЛИЦА «поле в строку» (владелец, 22.10.2026).
 * Раньше это были две независимые карточки рядом: строки не совпадали по
 * высоте, статус и отказ уезжали за край, треть высоты занимали аватары
 * 200×200. Теперь каждое поле — одна строка, слева и справа на одном уровне,
 * посередине — ✓ совпадает, ≈ похоже, ≠ разное. Вторая версия (по просьбе
 * «мало информативности»): строка-вывод сверху и группы «Личность и контакты /
 * У нас / Работа» — кто и когда добавил, воронки с этапами, история
 * переводов, отказ, места работы, общие навыки, ссылка на резюме.
 */
export function CompareTable({
  left,
  right,
  matched,
  signals,
  level,
}: {
  left: CompareSide;
  right: CompareSide | null;
  matched: (key: FieldKey | "name") => MatchKind;
  signals?: DupSignalLike[];
  level?: "exact" | "possible";
}) {
  const leftRej = useOwnRejections(left.entityId);
  const rightRej = useOwnRejections(right?.entityId);
  const leftAct = useActivity(left.entityId);
  const rightAct = useActivity(right?.entityId);
  const [showResume, setShowResume] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  if (!right) {
    return <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-slate-400">Загружаем анкету…</div>;
  }
  // Отметка строки: признак с бэка (matched) или просто одинаковые значения —
  // «Минск / Минск» тоже ✓, хотя город в дубль не засчитывается.
  const kindOf = (key: RowKey, a: string, b: string): MatchKind => {
    const same = !!a && !!b && norm(a) === norm(b);
    if (key === "position") return same ? "exact" : null;
    return matched(key) ?? (same ? "exact" : null);
  };
  const rowsOf = (group: (typeof GROUPS)[number]) =>
    group.rows
      .map(({ key, label }) => {
        const a = valueOf(left.side, key);
        const b = valueOf(right.side, key);
        const kind = kindOf(key, a, b);
        return { key, label, a, b, kind, differs: !kind && !!a && !!b && norm(a) !== norm(b) };
      })
      .filter((r) => r.a || r.b);
  const allRows = GROUPS.flatMap(rowsOf);
  // «ФИО» остаётся заглавными, остальное — строчными внутри фразы.
  const word = (label: string) => (label === label.toUpperCase() ? label : label.toLowerCase());
  const same = allRows.filter((r) => r.kind === "exact").map((r) => word(r.label));
  const alike = allRows.filter((r) => r.kind === "partial").map((r) => word(r.label));
  const diff = allRows.filter((r) => r.differs).map((r) => word(r.label));
  const fieldSignals = new Set(Object.values(SIGNAL_FIELD_TO_SIDE));
  const extraSignals = (signals || []).filter((sg) => !fieldSignals.has(SIGNAL_FIELD_TO_SIDE[sg.field]));
  const verdict = level === "exact" ? "Скорее всего, это один человек" : "Возможно, это один человек — сверьте";
  const verdictText = compareVerdictText({
    same,
    alike,
    extra: extraSignals.map((sg) => sg.label),
    diff,
  });

  const resumeLink = (s: Side) =>
    s.sourceUrl ? (
      <a href={s.sourceUrl} target="_blank" rel="noreferrer" className="text-[var(--hf-cyan-700)] hover:underline break-all">
        {s.sourceUrl.replace(/^https?:\/\/(www\.)?/, "").replace(/\?.*$/, "").slice(0, 48)} ↗
      </a>
    ) : empty;
  const added = (s: CompareSide) =>
    s.createdAt || s.createdBy ? (
      <span>{[shortDate(s.createdAt), s.createdBy, s.side.source].filter(Boolean).join(" · ")}</span>
    ) : empty;
  const jobs = (s: Side) =>
    s.jobs.length ? (
      <div className="space-y-0.5 text-[12px] text-slate-700">{s.jobs.map((j, i) => <div key={i}>{j}</div>)}</div>
    ) : empty;
  const commonJob = left.side.jobs.some((j) => {
    const company = norm(j.split("|")[1] || "");
    return company && right.side.jobs.some((k) => norm(k.split("|")[1] || "") === company);
  });

  return (
    <div className="space-y-2.5">
      {/* Вывод — одним предложением (владелец, 24.10.2026: плашки-обрывки
          читались как одна фраза, зачем-то разрезанная). Отказ — у имени анкеты. */}
      <p
        className="rounded-xl border px-3 py-2 text-[13px] leading-relaxed"
        style={level === "exact"
          ? { background: "#f3f8ec", borderColor: "#cfe3b4", color: "#27500a" }
          : { background: "#fff8e8", borderColor: "#f2d58f", color: "#713f00" }}
      >
        <span className="font-semibold">{verdict}.</span>
        {verdictText && <> {verdictText}</>}
      </p>

      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className={`${GRID} items-center`}>
          <div />
          <div className="p-3"><SideHead s={left} rejection={leftRej[0]} /></div>
          <div />
          <div className="p-3"><SideHead s={right} rejection={rightRej[0]} /></div>
        </div>

        {GROUPS.slice(0, 1).map((g) => (
          <div key={g.title}>
            <div className="border-t border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--hf-cyan-700)]">{g.title}</div>
            {rowsOf(g).map((r) => (
              <Row key={r.key} label={r.label} kind={r.kind} differs={r.differs}
                a={r.a || empty} b={r.b || empty} />
            ))}
            {(left.side.sourceUrl || right.side.sourceUrl) && (
              <Row label="Резюме" a={resumeLink(left.side)} b={resumeLink(right.side)}
                kind={matched("source") ?? null} />
            )}
          </div>
        ))}

        <div className="border-t border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--hf-cyan-700)]">У нас</div>
        <Row label="Добавлена" a={added(left)} b={added(right)} />
        <Row label="Воронки" a={<FunnelsCell blocks={leftAct} fallback={left.side} />} b={<FunnelsCell blocks={rightAct} fallback={right.side} />} />
        {(leftAct.some((b) => b.events.length) || rightAct.some((b) => b.events.length)) && (
          <Row label="История" a={<HistoryCell blocks={leftAct} />} b={<HistoryCell blocks={rightAct} />} />
        )}
        {(leftRej.length > 0 || rightRej.length > 0) && (
          <Row label="Отказ" a={<RejectionCell items={leftRej} />} b={<RejectionCell items={rightRej} />} tone="bg-[#fff7f7]" />
        )}
        <Row
          label="Комментарии"
          a={<span className={left.side.notes.length ? "" : "text-slate-300"}>{left.side.notes.length}</span>}
          b={
            <span className="flex items-center gap-2">
              <span className={right.side.notes.length ? "" : "text-slate-300"}>{right.side.notes.length}</span>
              {left.side.notes.length + right.side.notes.length > 0 && (
                <button type="button" className="text-[var(--hf-cyan-700)] hover:underline" onClick={() => setShowNotes((v) => !v)}>
                  {showNotes ? "скрыть" : "показать ▸"}
                </button>
              )}
            </span>
          }
        />
        {showNotes && (
          <div className={`${GRID} border-t border-slate-100`}>
            <div />
            <div className="p-3"><NotesList notes={left.side.notes} /></div>
            <div />
            <div className="p-3"><NotesList notes={right.side.notes} /></div>
          </div>
        )}

        {GROUPS.slice(1).map((g) => (
          <div key={g.title}>
            <div className="border-t border-slate-200 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--hf-cyan-700)]">{g.title}</div>
            {rowsOf(g).map((r) => (
              <Row key={r.key} label={r.label} kind={r.kind} differs={r.differs}
                a={r.a || empty} b={r.b || empty} />
            ))}
            {(left.side.jobs.length > 0 || right.side.jobs.length > 0) && (
              <Row label="Места работы" a={jobs(left.side)} b={jobs(right.side)} kind={commonJob ? "exact" : null} />
            )}
            {(left.side.skills.length > 0 || right.side.skills.length > 0) && (
              <Row label="Навыки"
                a={<SkillsCell mine={left.side.skills} other={right.side.skills} />}
                b={<SkillsCell mine={right.side.skills} other={left.side.skills} />} />
            )}
          </div>
        ))}

        <div className="border-t border-slate-200 px-3 py-2 text-[13px]">
          <button type="button" className="text-[var(--hf-cyan-700)] hover:underline" onClick={() => setShowResume((v) => !v)}>
            {showResume ? "Скрыть резюме" : "Открыть резюме обеих анкет ▸"}
          </button>
        </div>
        {showResume && (
          <div className="grid grid-cols-2 gap-4 border-t border-slate-100 p-3">
            {[left, right].map((sd) => (
              <div key={sd.entityId} className="min-w-0">
                <CompareResumePreview
                  entityId={sd.entityId}
                  extraData={sd.extraData}
                  parts={{ resumes: sd.side.resumes, text: sd.side.resumeText, extra: sd.side.resumeExtra }}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Одна карточка карусели похожих анкет. */
export type CarouselItem = {
  id: number;
  name: string;
  confidence: number;
  level?: "exact" | "possible";
  strength?: string;
  reason: string;
  decision?: "merged" | "dismissed";
  /** Короткая метка состояния: «Был отказ», этап… */
  badge?: { text: string; tone: "red" | "blue" | "gray" } | null;
  /** Кто это: должность · город · когда добавлена — чтобы различать анкеты, не открывая. */
  details?: string;
};

function Ring({ value, tone }: { value: number; tone: string }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      className="h-11 w-11 shrink-0 rounded-full p-[3px]"
      style={{ background: `conic-gradient(${tone} ${v}%, #ececec 0)` }}
      aria-label={`Уверенность ${v}%`}
    >
      <div className="flex h-full w-full items-center justify-center rounded-full bg-white text-[12.5px] font-bold" style={{ color: tone }}>
        {v}
      </div>
    </div>
  );
}

/**
 * Карусель похожих анкет — карточки с кольцом уверенности, причиной («имя +
 * телефон») и состоянием («Был отказ», «объединена»). Выбранная — в рамке.
 * Не влезают — горизонтальная прокрутка со стрелками по краям.
 */
export function DupCarousel({
  items,
  selectedId,
  onSelect,
}: {
  items: CarouselItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  const update = () => {
    const el = ref.current;
    if (!el) return;
    setEdges({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
  };
  useEffect(() => {
    update();
    const el = ref.current;
    el?.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      el?.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [items.length]);
  useEffect(() => {
    ref.current?.querySelector(`[data-dup="${selectedId}"]`)?.scrollIntoView({ behavior: "smooth", inline: "nearest", block: "nearest" });
  }, [selectedId]);
  const scrollBy = (dx: number) => ref.current?.scrollBy({ left: dx, behavior: "smooth" });
  return (
    <div className="relative">
      {edges.left && (
        <button type="button" aria-label="Назад" onClick={() => scrollBy(-260)}
          className="absolute left-0 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white px-2 py-1 text-slate-500 shadow">‹</button>
      )}
      <div ref={ref} className="flex gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
        {items.map((it) => {
          const current = it.id === selectedId;
          const tone = it.level === "exact" ? "#e24b4a" : "#ef9f27";
          const badge = it.decision === "merged"
            ? { text: "объединена", cls: "bg-lime-100 text-lime-800" }
            : it.decision === "dismissed"
              ? { text: "другой человек", cls: "bg-slate-100 text-slate-500" }
              : it.badge
                ? { text: it.badge.text, cls: it.badge.tone === "red" ? "bg-[#fdecec] text-[#a32d2d]" : it.badge.tone === "blue" ? "bg-blue-50 text-blue-800" : "bg-slate-100 text-slate-600" }
                : null;
          return (
            <button
              key={it.id}
              data-dup={it.id}
              type="button"
              onClick={() => onSelect(it.id)}
              title={it.details ? `${it.name} — ${it.details}` : it.name}
              className={`flex w-[330px] shrink-0 items-center gap-3 rounded-xl border bg-white px-3 py-2 text-left transition ${
                current ? "border-[var(--hf-cyan-700)] ring-2 ring-[var(--hf-cyan-700)]/30" : "border-slate-200 hover:border-slate-300"
              } ${it.decision ? "opacity-60" : ""}`}
            >
              {it.decision ? (
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-base ${it.decision === "merged" ? "bg-lime-100 text-lime-700" : "bg-slate-100 text-slate-500"}`}>
                  {it.decision === "merged" ? "✓" : "✕"}
                </div>
              ) : (
                <Ring value={it.confidence} tone={tone} />
              )}
              <div className="min-w-0">
                {/* Тот же состав, что был (кольцо, имя, этап, причина, «кто это»),
                    но плотнее: этап — рядом с именем, «кто это» — одной строкой. */}
                <div className="flex min-w-0 items-center gap-1.5">
                  <span className="truncate text-[13.5px] font-semibold text-slate-900">{it.name}</span>
                  {badge && <span className={`shrink-0 rounded-full px-1.5 py-[1px] text-[10.5px] font-semibold ${badge.cls}`}>{badge.text}</span>}
                </div>
                <div className="truncate text-[12px] text-slate-600">
                  {it.level === "exact" ? "точно · " : "возможно · "}{it.reason || "совпадение"}
                </div>
                {it.details && <div className="truncate text-[11.5px] text-slate-400">{it.details}</div>}
              </div>
            </button>
          );
        })}
      </div>
      {edges.right && (
        <button type="button" aria-label="Дальше" onClick={() => scrollBy(260)}
          className="absolute right-0 top-1/2 z-10 -translate-y-1/2 rounded-full bg-white px-2 py-1 text-slate-500 shadow">›</button>
      )}
    </div>
  );
}

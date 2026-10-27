import type { ApplicationStage, EntityStatus } from "@/types";

// Справочник этапов HR — ОДИН на весь фронт (рефакторинг 20.10.2026).
//
// До этого подписи, цвета и порядок этапов были переписаны в семи местах
// (types, карточка, «Все кандидаты», воронки, рабочие пространства, окно
// настройки этапов вакансии…), и копии разъехались: «Перешёл в отдел» в
// воронке был салатовым, а в списке зелёным; в рабочих пространствах не было
// «Практики», «Перешёл в отдел» и «Резерва»; в настройке этапов вакансии
// пропадал «Резерв».
//
// Порядок строк = порядок колонок. Пара на сервере — backend/api/services/
// hr_stages.py (подписи и цвета держать одинаковыми).

export type StageColor =
  | "blue"
  | "cyan"
  | "purple"
  | "indigo"
  | "orange"
  | "yellow"
  | "green"
  | "teal"
  | "red"
  | "gray";

export interface HrStage {
  /** Этап заявки (воронки). */
  stage: ApplicationStage;
  /** Тот же этап как общий статус кандидата («Все кандидаты»). */
  status: EntityStatus;
  label: string;
  color: StageColor;
  /** Есть вкладка в воронке («Отозван» — только на доске «Все кандидаты»). */
  inFunnel: boolean;
}

export const HR_STAGES: readonly HrStage[] = [
  { stage: "applied", status: "new", label: "Новый", color: "blue", inFunnel: true },
  { stage: "screening", status: "screening", label: "Выполняет ТЗ", color: "cyan", inFunnel: true },
  { stage: "phone_screen", status: "practice", label: "Интервью с HR", color: "purple", inFunnel: true },
  { stage: "interview", status: "tech_practice", label: "Интервью с заказчиком", color: "indigo", inFunnel: true },
  { stage: "assessment", status: "is_interview", label: "Принятие решения", color: "orange", inFunnel: true },
  { stage: "offer", status: "offer", label: "Выставлен оффер", color: "yellow", inFunnel: true },
  { stage: "hired", status: "hired", label: "Оффер принят", color: "green", inFunnel: true },
  { stage: "probation", status: "probation", label: "Практика", color: "teal", inFunnel: true },
  { stage: "transferred", status: "transferred", label: "Перешёл в отдел", color: "green", inFunnel: true },
  { stage: "rejected", status: "rejected", label: "Отказ", color: "red", inFunnel: true },
  { stage: "withdrawn", status: "withdrawn", label: "Отозван", color: "gray", inFunnel: false },
  { stage: "reserve", status: "reserve", label: "Резерв", color: "gray", inFunnel: true },
];

/** Колонка «Все кандидаты» для статусов вне воронки (BOARD_OTHER_STATUS). */
export const BOARD_OTHER_LABEL = "Вне воронки";

/**
 * Уволен / уволился — итог после отдела. Своей вкладки на «Все кандидаты» нет:
 * для HR это отказ (Мария, 20.10.2026: «борд и АТС — единая система»), и
 * стоят они во вкладке «Отказ». В паре с services/hr_stages.py (board_column).
 */
export const DEPARTED_LABELS: Record<string, string> = {
  dismissed: "Уволен",
  quit: "Уволился",
};
const COLUMN_OF_STATUS: Record<string, string> = { dismissed: "rejected", quit: "rejected" };

/** Вкладка «Все кандидаты», в которой стоит кандидат с этим статусом. */
export function boardColumnOf(status: string): string {
  if (HR_STAGES.some((s) => s.status === status)) return status;
  return COLUMN_OF_STATUS[status] ?? "other";
}

/** Этапы заявки в порядке вкладок воронки. */
export const FUNNEL_STAGE_ORDER: ApplicationStage[] = HR_STAGES.filter((s) => s.inFunnel).map(
  (s) => s.stage,
);

/** Подпись по этапу заявки. */
export const STAGE_LABEL_BY_STAGE = Object.fromEntries(
  HR_STAGES.map((s) => [s.stage, s.label]),
) as Record<ApplicationStage, string>;

/** Подпись по статусу кандидата (только этапы HR). */
export const STAGE_LABEL_BY_STATUS = Object.fromEntries(
  HR_STAGES.map((s) => [s.status, s.label]),
) as Record<string, string>;

/** Статус кандидата → этап заявки и обратно. */
export const STAGE_BY_STATUS = Object.fromEntries(
  HR_STAGES.map((s) => [s.status, s.stage]),
) as Record<string, ApplicationStage>;
export const STATUS_BY_STAGE = Object.fromEntries(
  HR_STAGES.map((s) => [s.stage, s.status]),
) as Record<ApplicationStage, EntityStatus>;

/** Цвет по этапу заявки. */
export const STAGE_COLOR_BY_STAGE = Object.fromEntries(
  HR_STAGES.map((s) => [s.stage, s.color]),
) as Record<ApplicationStage, StageColor>;

// ── Классы Tailwind по цвету. Строки целиком (не собираем из кусочков):
// Tailwind находит классы в исходниках только в таком виде.

/** Бледная плашка этапа (бейдж). */
export const STAGE_BADGE_CLASS: Record<StageColor, string> = {
  blue: "bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)] border-[color:var(--hf-accent-border-30)]",
  cyan: "bg-[var(--hf-status-cyan-badge)] text-[var(--hf-status-cyan)] border-[color:var(--hf-status-cyan-badge)]",
  purple: "bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)] border-[color:var(--hf-status-purple-badge)]",
  indigo: "bg-[var(--hf-status-indigo-badge)] text-[var(--hf-status-indigo)] border-[color:var(--hf-status-indigo-badge)]",
  orange: "bg-[var(--hf-status-orange-badge)] text-[var(--hf-status-orange)] border-[color:var(--hf-status-orange-badge)]",
  yellow: "bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)] border-[color:var(--hf-status-yellow-badge)]",
  green: "bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)] border-[color:var(--hf-status-green-badge)]",
  teal: "bg-[var(--hf-status-teal-badge)] text-[var(--hf-status-teal)] border-[color:var(--hf-status-teal-badge)]",
  red: "bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)] border-[color:var(--hf-status-red-badge)]",
  gray: "bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)] border-[color:var(--hf-status-gray-badge)]",
};

/** Яркий чип: сплошной цвет этапа + тёмный текст той же гаммы. */
export const STAGE_CHIP_BRIGHT_CLASS: Record<StageColor, string> = {
  blue: "bg-[var(--hf-status-blue)] text-[#0b2a4a]",
  cyan: "bg-[var(--hf-status-cyan)] text-[#083344]",
  purple: "bg-[var(--hf-status-purple)] text-[#3b0764]",
  indigo: "bg-[var(--hf-status-indigo)] text-[#1e1b4b]",
  orange: "bg-[var(--hf-status-orange)] text-[#431407]",
  yellow: "bg-[var(--hf-status-yellow)] text-[#422006]",
  green: "bg-[var(--hf-status-green)] text-[#052e16]",
  teal: "bg-[var(--hf-status-teal)] text-[#042f2e]",
  red: "bg-[var(--hf-status-red)] text-[#450a0a]",
  gray: "bg-[var(--hf-status-gray)] text-[#111827]",
};

/** Яркий чип по этапу заявки (шапка «Этапы по воронкам», строка списка). */
export const STAGE_CHIP_BRIGHT_BY_STAGE = Object.fromEntries(
  HR_STAGES.map((s) => [s.stage, STAGE_CHIP_BRIGHT_CLASS[s.color]]),
) as Record<string, string>;

/** Набор для вкладок и колонок воронки: фон, текст, точка, бейдж. */
export type StageTabColors = { bg: string; text: string; dot: string; badge: string };
export const STAGE_TAB_COLORS: Record<StageColor, StageTabColors> = {
  blue: { bg: "bg-[var(--hf-status-blue-bg)]", text: "text-[var(--hf-status-blue)]", dot: "bg-[var(--hf-status-blue)]", badge: "bg-[var(--hf-status-blue-badge)] text-[var(--hf-status-blue)]" },
  cyan: { bg: "bg-[var(--hf-status-cyan-bg)]", text: "text-[var(--hf-cyan-400)]", dot: "bg-[var(--hf-status-cyan)]", badge: "bg-[var(--hf-status-cyan-badge)] text-[var(--hf-cyan-400)]" },
  purple: { bg: "bg-[var(--hf-status-purple-bg)]", text: "text-[var(--hf-status-purple)]", dot: "bg-[var(--hf-status-purple)]", badge: "bg-[var(--hf-status-purple-badge)] text-[var(--hf-status-purple)]" },
  indigo: { bg: "bg-[var(--hf-status-indigo-bg)]", text: "text-[var(--hf-status-indigo)]", dot: "bg-[var(--hf-status-indigo)]", badge: "bg-[var(--hf-status-indigo-badge)] text-[var(--hf-status-indigo)]" },
  orange: { bg: "bg-[var(--hf-status-orange-bg)]", text: "text-[var(--hf-status-orange)]", dot: "bg-[var(--hf-status-orange)]", badge: "bg-[var(--hf-status-orange-badge)] text-[var(--hf-status-orange)]" },
  yellow: { bg: "bg-[var(--hf-status-yellow-bg)]", text: "text-[var(--hf-status-yellow)]", dot: "bg-[var(--hf-status-yellow)]", badge: "bg-[var(--hf-status-yellow-badge)] text-[var(--hf-status-yellow)]" },
  green: { bg: "bg-[var(--hf-status-green-bg)]", text: "text-[var(--hf-status-green)]", dot: "bg-[var(--hf-status-green)]", badge: "bg-[var(--hf-status-green-badge)] text-[var(--hf-status-green)]" },
  teal: { bg: "bg-[var(--hf-status-teal-bg)]", text: "text-[var(--hf-status-teal)]", dot: "bg-[var(--hf-status-teal)]", badge: "bg-[var(--hf-status-teal-badge)] text-[var(--hf-status-teal)]" },
  red: { bg: "bg-[var(--hf-status-red-bg)]", text: "text-[var(--hf-status-red)]", dot: "bg-[var(--hf-status-red)]", badge: "bg-[var(--hf-status-red-badge)] text-[var(--hf-status-red)]" },
  gray: { bg: "bg-[var(--hf-status-gray-bg)]", text: "text-[var(--hf-status-gray)]", dot: "bg-[var(--hf-status-gray)]", badge: "bg-[var(--hf-status-gray-badge)] text-[var(--hf-status-gray)]" },
};

/** Цвета вкладки по этапу заявки. */
export const stageTabColors = (stage: string): StageTabColors | undefined => {
  const color = STAGE_COLOR_BY_STAGE[stage as ApplicationStage];
  return color ? STAGE_TAB_COLORS[color] : undefined;
};

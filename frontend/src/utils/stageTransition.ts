/**
 * Поля окна «Сменить этап подбора» при переводе в «Практика» и «Перешёл в отдел»
 * (мит 19.11.2026, Мария: «переводим на статус и вносим все коррективы сразу на
 * старте» — дата старта, ментор, отдел). Дату практики раньше ставил бот сам
 * (следующий рабочий день), и «девочки забудут» её поправить; теперь она в окне,
 * уже подставленная, и без неё перевести нельзя. По этой дате бот (handoff.py)
 * планирует практику — поэтому дату пишем ДО смены статуса.
 */

export type TransitionStage = "probation" | "transferred";

export interface TransitionFields {
  /** YYYY-MM-DD: выход на практику / выход в отдел. */
  date: string;
  /** Ментор практики (тег у ФИО); "" — не менять. */
  mentor: string;
  /** Отдел при переходе; null — не менять. */
  departmentId: number | null;
}

export function isTransitionStage(stage: string): stage is TransitionStage {
  return stage === "probation" || stage === "transferred";
}

function iso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Следующий рабочий день (сб/вс пропускаем) — как ставит бот, если даты нет. */
export function nextWorkday(today: Date): string {
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  return iso(d);
}

function storedDate(value: unknown): string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : "";
}

/** Что подставить при открытии: уже вписанная дата, иначе завтра (практика) / сегодня (отдел). */
export function transitionDefaults(
  stage: TransitionStage,
  extra: Record<string, unknown> | undefined,
  today: Date,
): TransitionFields {
  if (stage === "probation") {
    return { date: storedDate(extra?.practice_start_date) || nextWorkday(today), mentor: "", departmentId: null };
  }
  return { date: storedDate(extra?.department_transfer_date) || iso(today), mentor: "", departmentId: null };
}

/** Можно сохранять: дата обязательна и настоящая. */
export function transitionReady(fields: TransitionFields | null): boolean {
  return !!fields && /^\d{4}-\d{2}-\d{2}$/.test(fields.date) && !Number.isNaN(Date.parse(fields.date));
}

export interface TransitionApi {
  updateRow: (entityId: number, patch: Record<string, string>) => Promise<unknown>;
  setMentor: (entityId: number, name: string) => Promise<unknown>;
  addPlacement: (entityId: number, departmentId: number) => Promise<unknown>;
}

/** Пишет поля в карточку. Порядок: отдел → дата → ментор; смену статуса зовут ПОСЛЕ. */
export async function applyTransitionFields(
  entityId: number,
  stage: TransitionStage,
  fields: TransitionFields,
  api: TransitionApi,
): Promise<void> {
  if (stage === "transferred" && fields.departmentId != null) {
    await api.addPlacement(entityId, fields.departmentId);
  }
  const key = stage === "probation" ? "practice_start_date" : "department_start_date";
  await api.updateRow(entityId, { [key]: fields.date });
  if (stage === "probation" && fields.mentor) {
    await api.setMentor(entityId, fields.mentor);
  }
}
